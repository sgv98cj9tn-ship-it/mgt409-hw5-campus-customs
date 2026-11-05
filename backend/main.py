"""FastAPI backend for the Campus Customs dashboard.

Start it from the backend/ folder:
    uvicorn main:app --reload --port 8000
Then open http://localhost:8000/docs to try every route in the browser.

Routes
    GET  /tickets                      the three tickets, open or resolved
    POST /tickets/{ticket_id}/run      run the agent team on one ticket (resolved if nothing needs a human)
    GET  /events                       recent agent events from output/audit_trail.json
    GET  /approvals                    actions waiting for a human (so the board knows what to approve)
    POST /approvals/{approval_id}/approve   a human approves a payment or purchase; the only route that moves cash
    POST /approvals/{approval_id}/send      a human sends (optionally edited) customer message; simulated, nothing is emailed
    POST /approvals/{approval_id}/approve-price   a human approves a discount; checked against cost, no cash moves
    GET  /cash                         current checking balance from cash_accounts
    POST /reset                        restore campus_customs_new.db from the original campus_customs.db

Safety: the agents reach the shop only through the MCP tools in backend/mcp_client.py. None of
those tools can pay anything, and no agent can call these HTTP routes. Paying happens here, in
approve_payment, and only for a request an agent queued with request_human_approval.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

# Running "uvicorn main:app" from backend/ puts backend/ on the path, not Homework 5/.
# Add Homework 5/ so the "backend.*" imports below resolve either way.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import audit  # noqa: E402
from backend.agents import run_ticket  # noqa: E402
from backend.config import AUDIT_TRAIL_PATH, DB_PATH, ORIGINAL_DB_PATH  # noqa: E402
from backend.mcp_client import leaked_terms, shop_toolset  # noqa: E402
from backend import resolved_export  # noqa: E402

CHECKING = "checking"
PAYABLE_ACTIONS = ("payment", "purchase_order")

# One agent run or reset at a time, so two runs never write the same tickets at once.
run_lock = asyncio.Lock()
# The ticket the crew is working on right now. While it's set, human decisions on that ticket
# wait: the agents shouldn't see a payment or a sent reply land in the middle of their run, and
# the ticket only counts as resolved once the run itself finishes.
running_ticket: int | None = None


def _not_while_running(ticket_id: int | None) -> None:
    if ticket_id is not None and ticket_id == running_ticket:
        raise HTTPException(409, f"The crew is still working ticket {ticket_id}. "
                                 "Approve this once the run finishes.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with shop_toolset():  # one MCP server connection for the life of the backend
        yield


app = FastAPI(title="Campus Customs backend", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- database helpers

def _db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(500, f"Database not found: {DB_PATH.name}. POST /reset to restore it.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _desk_date(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]


def _checking(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (CHECKING,)).fetchone()
    if row is None:
        raise HTTPException(500, "No checking account in cash_accounts.")
    return {"account": row["name"], "balance": round(row["balance"], 2), "as_of": row["date"]}


def _human_event(event: str, ticket_id: int | None, **data: Any) -> None:
    audit.record(event, run_id="human", ticket_id=ticket_id, agent="Human", depth=0, **data)


def _settle_ticket(conn: sqlite3.Connection, ticket_id: int | None) -> tuple[str | None, int]:
    """Set a ticket's status from its approval queue: resolved when nothing is waiting on a
    human, awaiting_approval while anything is. Returns (status, pending count)."""
    if ticket_id is None:
        return None, 0
    pending = conn.execute("SELECT COUNT(*) FROM approval_requests WHERE ticket_id = ? AND status = 'pending'",
                           (ticket_id,)).fetchone()[0] if _has_table(conn, "approval_requests") else 0
    status = "resolved" if pending == 0 else "awaiting_approval"
    conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    return status, pending


def _after_human_decision(ticket_id: int | None, before: str | None, after: str | None) -> None:
    """Log the moment a human's last decision resolves a ticket."""
    if after == "resolved" and before != "resolved":
        _human_event("ticket_resolved", ticket_id, pending_approvals=0)


def _export() -> None:
    """Keep output/resolved_tickets.json current. A failed export never breaks a route."""
    try:
        resolved_export.write()
    except Exception as exc:  # noqa: BLE001
        print(f"[export] could not write resolved_tickets.json: {exc}")


# ---------------------------------------------------------------- tickets

@app.get("/tickets")
def list_tickets() -> dict[str, Any]:
    """The tickets, each marked open or resolved, with any approvals waiting on a human."""
    with _db() as conn:
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        pending: dict[int, int] = {}
        if _has_table(conn, "approval_requests"):
            for r in conn.execute("SELECT ticket_id, COUNT(*) AS n FROM approval_requests "
                                  "WHERE status = 'pending' GROUP BY ticket_id"):
                pending[r["ticket_id"]] = r["n"]
        today = _desk_date(conn)
    tickets = []
    for r in rows:
        t = dict(r)
        t["state"] = "resolved" if (t["status"] or "").lower() == "resolved" else "open"
        t["pending_approvals"] = pending.get(t["id"], 0)
        t["running"] = t["id"] == running_ticket
        tickets.append(t)
    return {"today": today, "tickets": tickets}


@app.post("/tickets/{ticket_id}/run")
async def run_ticket_route(ticket_id: int) -> dict[str, Any]:
    """Run the agent team (Boss first) on one ticket. Takes a minute or two; every step goes
    to the audit trail, so GET /events shows progress while it runs."""
    with _db() as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            raise HTTPException(404, f"No ticket {ticket_id}.")
    if run_lock.locked():
        raise HTTPException(409, "Another ticket run or reset is in progress. Try again when it finishes.")
    global running_ticket
    async with run_lock:
        running_ticket = ticket_id
        try:
            result = await run_ticket(ticket_id)
        except Exception as exc:  # noqa: BLE001 - report the failure to the dashboard
            _export()
            raise HTTPException(502, f"The agent run failed: {type(exc).__name__}: {str(exc)[:300]}") from exc
        finally:
            running_ticket = None
    # The run finished. The ticket is resolved only if nothing the agents queued still needs a
    # human; otherwise it waits as awaiting_approval until the last approval is decided.
    with _db() as conn:
        agent_status = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()["status"]
        status, pending = _settle_ticket(conn, ticket_id)
        conn.commit()
    audit.record("ticket_resolved" if status == "resolved" else "crew_finished", run_id=result["run_id"],
                 ticket_id=ticket_id, agent="Boss", depth=0, agent_status=agent_status, pending_approvals=pending)
    result.update(ticket_status=status, agent_status=agent_status, pending_approvals=pending)
    _export()
    return result


# ---------------------------------------------------------------- events

def _summarize(event: dict[str, Any]) -> dict[str, Any]:
    """Boil one audit line down to who acted, what they said, and which tools they used."""
    said: list[str] = []
    tools: list[dict[str, Any]] = []
    for part in event.get("parts", []):
        if part.get("kind") == "text":
            said.append(part["content"])
        elif part.get("kind") == "tool_call":
            tools.append({"tool": part["tool"], "args": part.get("args")})
    output = event.get("output")
    if isinstance(output, dict) and output.get("summary"):
        said.append(output["summary"])
    out = {k: event.get(k) for k in ("ts", "run_id", "ticket_id", "agent", "depth", "event")}
    out["said"] = " ".join(said) or None
    out["tools"] = tools
    for key in ("to_agent", "task", "status", "reason", "error", "approval_id", "amount", "payee", "recipient",
                "edited", "message",
                "kind", "approved_by", "checking_after", "agent_status", "pending_approvals"):
        if key in event:
            out[key] = event[key]
    if output is not None:
        out["output"] = output
    return out


@app.get("/events")
def recent_events(limit: int = Query(50, ge=1, le=500), ticket_id: int | None = None,
                  run_id: str | None = None, since: str | None = None) -> dict[str, Any]:
    """The most recent agent events, oldest first. Model requests (which only carry tool results
    back to the model) are skipped; the tool calls themselves appear on model_response events.
    `since` (an ISO time) keeps only events at or after it, for a live feed of the current run."""
    if not AUDIT_TRAIL_PATH.exists():
        return {"events": [], "count": 0}
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
    except ValueError as exc:
        raise HTTPException(400, "since must be an ISO date-time.") from exc
    events = []
    with AUDIT_TRAIL_PATH.open(encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "model_request":
                continue
            if ticket_id is not None and e.get("ticket_id") != ticket_id:
                continue
            if run_id and e.get("run_id") != run_id:
                continue
            if since_dt and datetime.fromisoformat(e["ts"]) < since_dt.replace(microsecond=0):
                continue
            events.append(e)
    events = [_summarize(e) for e in events[-limit:]]
    return {"events": events, "count": len(events)}


# ---------------------------------------------------------------- approvals and paying

@app.get("/approvals")
def list_approvals(status: str | None = "pending", ticket_id: int | None = None) -> dict[str, Any]:
    """Approval requests the agents queued. Default: the ones still waiting on a human."""
    with _db() as conn:
        if not _has_table(conn, "approval_requests"):
            return {"approvals": []}
        where, params = [], []
        if status:
            where.append("status = ?")
            params.append(status)
        if ticket_id is not None:
            where.append("ticket_id = ?")
            params.append(ticket_id)
        sql = "SELECT * FROM approval_requests" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
        return {"approvals": [dict(r) for r in conn.execute(sql, params)]}


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human who clicked approve.")


def _what_it_pays(conn: sqlite3.Connection, req: sqlite3.Row) -> tuple[str, int, float, str]:
    """Work out what an approved request pays for: (kind, ref_id, amount owed, payee).
    Checks it against the real invoice or lease so an agent's numbers can't move cash."""
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()

    if req["action_type"] == "purchase_order":
        if not req["amount"] or req["amount"] <= 0:
            raise HTTPException(409, "This purchase order has no amount.")
        return "purchase_order", req["id"], req["amount"], req["payee"] or "vendor"

    if ticket is not None and ticket["invoice_id"]:
        inv = conn.execute("SELECT i.*, v.name AS vendor FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                           "WHERE i.id = ?", (ticket["invoice_id"],)).fetchone()
        if inv is not None:
            paid = conn.execute("SELECT 1 FROM payments WHERE kind = 'invoice' AND ref_id = ?", (inv["id"],)).fetchone()
            if inv["status"].lower() == "paid" or paid:
                raise HTTPException(409, f"Invoice {inv['id']} is already paid.")
            return "invoice", inv["id"], inv["amount"], inv["vendor"]

    if ticket is not None and ticket["lease_id"]:
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)).fetchone()
        if lease is not None:
            due = datetime.fromisoformat(lease["next_due"]).date()
            cycle_start = due.replace(month=due.month - 1) if due.month > 1 else due.replace(year=due.year - 1, month=12)
            paid = conn.execute("SELECT 1 FROM payments WHERE kind = 'rent' AND ref_id = ? AND substr(paid_at, 1, 10) > ?",
                                (lease["id"], cycle_start.isoformat())).fetchone()
            if paid:
                raise HTTPException(409, f"Rent for lease {lease['id']} due {lease['next_due']} is already paid.")
            return "rent", lease["id"], lease["monthly_rent"], lease["landlord"]

    raise HTTPException(409, "Can't tell which invoice or lease this payment is for, so nothing was paid.")


@app.post("/approvals/{approval_id}/approve")
def approve_payment(approval_id: int, body: ApproveBody) -> dict[str, Any]:
    """A human approves a payment or purchase. This is the only place cash changes:
    it records the payment, takes it out of checking, marks the invoice paid, and closes
    the approval request. Agents can only queue requests; they can't call this route."""
    with _db() as conn:
        if not _has_table(conn, "approval_requests"):
            raise HTTPException(404, "No approval requests yet.")
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,)).fetchone()
        if req is None:
            raise HTTPException(404, f"No approval request {approval_id}.")
        if req["status"] != "pending":
            raise HTTPException(409, f"Approval request {approval_id} is already {req['status']}.")
        if req["action_type"] not in PAYABLE_ACTIONS:
            raise HTTPException(400, f"Request {approval_id} is a {req['action_type']}, not a payment or purchase.")

        _not_while_running(req["ticket_id"])
        kind, ref_id, owed, payee = _what_it_pays(conn, req)
        if req["amount"] is not None and abs(req["amount"] - owed) > 0.005:
            raise HTTPException(409, f"The request asks for ${req['amount']:,.2f} but the {kind} is ${owed:,.2f}. "
                                     "Nothing was paid; have the agents re-check it.")
        cash = _checking(conn)
        if cash["balance"] < owed:
            raise HTTPException(409, f"Checking has ${cash['balance']:,.2f}, not enough for ${owed:,.2f}.")

        today = _desk_date(conn)
        now = datetime.now().isoformat(timespec="seconds")
        new_balance = round(cash["balance"] - owed, 2)
        cur = conn.execute("INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (kind, ref_id, owed, CHECKING, today, body.approved_by))
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, CHECKING))
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        conn.execute("UPDATE approval_requests SET status = 'approved', decided_by = ?, decided_at = ? WHERE id = ?",
                     (body.approved_by, now, approval_id))
        before = ticket_status = None
        if req["ticket_id"] is not None:
            before = conn.execute("SELECT status FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()[0]
            note = f"{kind} ${owed:,.2f} to {payee} approved by {body.approved_by} and paid from checking."
            conn.execute("UPDATE tickets SET notes = COALESCE(notes || char(10), '') || ? WHERE id = ?",
                         (note, req["ticket_id"]))
            ticket_status, _ = _settle_ticket(conn, req["ticket_id"])
        conn.commit()

    _human_event("payment_approved", req["ticket_id"], approval_id=approval_id, kind=kind, ref_id=ref_id,
                 amount=owed, payee=payee, approved_by=body.approved_by, checking_after=new_balance)
    _after_human_decision(req["ticket_id"], before, ticket_status)
    _export()
    return {"ok": True, "approval_id": approval_id, "payment_id": cur.lastrowid, "kind": kind, "ref_id": ref_id,
            "amount": owed, "payee": payee, "approved_by": body.approved_by,
            "checking_before": cash["balance"], "checking_after": new_balance, "ticket_status": ticket_status}


class SendBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human who approved the message.")
    message: str | None = Field(default=None, description="The text to send, if the human edited the draft.")


def _internal_names(conn: sqlite3.Connection, ticket_id: int | None) -> list[str]:
    names = [r[0] for r in conn.execute("SELECT name FROM vendors")]
    names += [r[0] for r in conn.execute("SELECT landlord FROM leases")]
    names += [r[0] for r in conn.execute("SELECT requester FROM tickets WHERE id != ?", (ticket_id or -1,))]
    return [n for n in names if n]


@app.post("/approvals/{approval_id}/send")
def send_customer_message(approval_id: int, body: SendBody) -> dict[str, Any]:
    """A human approves a customer message (as drafted, or after editing it) and sends it.

    For this project, sending is simulated: nothing is emailed or messaged. The request is marked
    sent with the final text, the ticket gets a note (and is resolved if nothing else is waiting), and the event goes
    to the audit trail and output/resolved_tickets.json. The same no-internal-info check the
    agents face runs on the final text, so an edit can't leak costs, vendors, rent, or other customers."""
    with _db() as conn:
        if not _has_table(conn, "approval_requests"):
            raise HTTPException(404, "No approval requests yet.")
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,)).fetchone()
        if req is None:
            raise HTTPException(404, f"No approval request {approval_id}.")
        if req["status"] != "pending":
            raise HTTPException(409, f"Approval request {approval_id} is already {req['status']}.")
        if req["action_type"] != "customer_message":
            raise HTTPException(400, f"Request {approval_id} is a {req['action_type']}, not a customer message.")

        _not_while_running(req["ticket_id"])
        draft = (req["draft_message"] or "").strip()
        text = (body.message if body.message is not None else draft).strip()
        if not text:
            raise HTTPException(400, "The message is empty.")
        hits = leaked_terms(text, _internal_names(conn, req["ticket_id"]))
        if hits:
            raise HTTPException(422, "This message shows internal information to the customer ("
                                     + ", ".join(sorted(set(hits))) + "). Edit it out, then send.")

        cols = {r["name"] for r in conn.execute("PRAGMA table_info(approval_requests)")}
        if "final_message" not in cols:
            conn.execute("ALTER TABLE approval_requests ADD COLUMN final_message TEXT")
        ticket = conn.execute("SELECT requester FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()
        recipient = ticket["requester"] if ticket else "the customer"
        edited = text != draft
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("UPDATE approval_requests SET status = 'sent', decided_by = ?, decided_at = ?, final_message = ? "
                     "WHERE id = ?", (body.approved_by, now, text, approval_id))
        before = ticket_status = None
        if req["ticket_id"] is not None:
            before = conn.execute("SELECT status FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()[0]
            note = (f"Customer message to {recipient} {'edited and ' if edited else ''}approved by {body.approved_by} "
                    "and marked sent (simulated; nothing was emailed).")
            conn.execute("UPDATE tickets SET notes = COALESCE(notes || char(10), '') || ? WHERE id = ?",
                         (note, req["ticket_id"]))
            ticket_status, _ = _settle_ticket(conn, req["ticket_id"])
        conn.commit()

    _human_event("customer_message_sent", req["ticket_id"], approval_id=approval_id, recipient=recipient,
                 approved_by=body.approved_by, edited=edited, message=text, simulated=True)
    _after_human_decision(req["ticket_id"], before, ticket_status)
    _export()
    return {"ok": True, "approval_id": approval_id, "recipient": recipient, "edited": edited, "message": text,
            "ticket_status": ticket_status, "simulated": True}


@app.post("/approvals/{approval_id}/approve-price")
def approve_price_override(approval_id: int, body: ApproveBody) -> dict[str, Any]:
    """A human approves a discount (price override) the agents proposed. No cash moves: this
    only okays the price. If the request names a price, it's checked against unit cost first,
    so nothing is approved at or below cost. The request is closed, the ticket gets a note, and
    the ticket is marked resolved once nothing else on it is waiting."""
    with _db() as conn:
        if not _has_table(conn, "approval_requests"):
            raise HTTPException(404, "No approval requests yet.")
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,)).fetchone()
        if req is None:
            raise HTTPException(404, f"No approval request {approval_id}.")
        if req["status"] != "pending":
            raise HTTPException(409, f"Approval request {approval_id} is already {req['status']}.")
        if req["action_type"] != "price_override":
            raise HTTPException(400, f"Request {approval_id} is a {req['action_type']}, not a price override.")

        _not_while_running(req["ticket_id"])
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()
        check = None
        if ticket is not None and ticket["sku"] and req["amount"]:
            price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (ticket["sku"],)).fetchone()
            if price is not None:
                qty = ticket["qty"] or 1
                # The amount may be a unit price or an order total; read it the way that fits.
                unit = req["amount"] if req["amount"] <= price["list_price"] else req["amount"] / qty
                if unit <= price["unit_cost"]:
                    raise HTTPException(409, f"That price (${unit:,.2f} a unit) is at or below cost. Nothing was approved.")
                check = {"unit_price": round(unit, 2), "list_price": price["list_price"], "qty": qty,
                         "discount_percent": round((1 - unit / price["list_price"]) * 100, 1),
                         "order_total": round(unit * qty, 2)}

        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("UPDATE approval_requests SET status = 'approved', decided_by = ?, decided_at = ? WHERE id = ?",
                     (body.approved_by, now, approval_id))
        before = ticket_status = None
        if req["ticket_id"] is not None:
            before = conn.execute("SELECT status FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()[0]
            detail = f" (${check['unit_price']:,.2f} a unit, {check['discount_percent']}% off)" if check else ""
            note = f"Price override{detail} approved by {body.approved_by}. No cash moved."
            conn.execute("UPDATE tickets SET notes = COALESCE(notes || char(10), '') || ? WHERE id = ?",
                         (note, req["ticket_id"]))
            ticket_status, _ = _settle_ticket(conn, req["ticket_id"])
        conn.commit()

    _human_event("price_override_approved", req["ticket_id"], approval_id=approval_id, approved_by=body.approved_by,
                 amount=req["amount"], price_check=check)
    _after_human_decision(req["ticket_id"], before, ticket_status)
    _export()
    return {"ok": True, "approval_id": approval_id, "approved_by": body.approved_by, "price_check": check,
            "ticket_status": ticket_status, "cash_moved": False}


# ---------------------------------------------------------------- cash and reset

@app.get("/cash")
def cash_balance() -> dict[str, Any]:
    """The current checking balance."""
    with _db() as conn:
        return _checking(conn)


@app.post("/reset")
async def reset_database() -> dict[str, Any]:
    """Restore campus_customs_new.db from the untouched original, for a fresh run.
    Tickets, cash, invoices, and payments go back to their starting values and the approval
    queue is cleared. The audit trail is never wiped; a db_reset event is added to it."""
    if not ORIGINAL_DB_PATH.exists():
        raise HTTPException(500, f"Original database not found: {ORIGINAL_DB_PATH.name}.")
    if run_lock.locked():
        raise HTTPException(409, "A ticket run is in progress. Reset after it finishes.")
    async with run_lock:
        src = sqlite3.connect(f"{ORIGINAL_DB_PATH.as_uri()}?mode=ro", uri=True)
        dst = sqlite3.connect(DB_PATH)
        try:
            src.backup(dst)  # copies page by page under SQLite's own locks
        finally:
            src.close()
            dst.close()
    _human_event("db_reset", None, source=ORIGINAL_DB_PATH.name, target=DB_PATH.name)
    _export()
    with _db() as conn:
        return {"ok": True, "message": f"{DB_PATH.name} restored from {ORIGINAL_DB_PATH.name}.",
                "cash": _checking(conn), "tickets": [dict(r) for r in conn.execute("SELECT id, status FROM tickets")]}
