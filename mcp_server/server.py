"""Campus Customs operations MCP server (HW5).

Tools for the Campus Customs agent team. Every tool uses the working copy
../data/campus_customs_new.db (never the original campus_customs.db) and only
returns what is in the database. "Today" is desk.date_today, not the real clock.

Read tools open the database read-only. The only writes are internal
bookkeeping: ticket status/notes (update_ticket) and the human approval queue
(request_human_approval). No tool pays, orders, or messages anyone.

Run from this folder (stdio):  python server.py
Run (HTTP):                    python server.py --http
HTTP URL:                      http://127.0.0.1:8002/mcp
Set CAMPUS_CUSTOMS_DB to point the server at another copy (used for tests).
"""

from __future__ import annotations

import argparse
import calendar
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB") or ROOT / "data" / "campus_customs_new.db")

mcp = FastMCP("campus-customs-ops")

TicketStatus = Literal["open", "in_progress", "awaiting_approval", "blocked"]
ApprovalAction = Literal["payment", "purchase_order", "customer_message", "price_override", "other"]


def _connect() -> sqlite3.Connection:
    """Open the working copy read-only, so read tools can't change it."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_write() -> sqlite3.Connection:
    """Open the working copy for the two bookkeeping tools that write."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_approvals_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS approval_requests (
            id INTEGER PRIMARY KEY,
            ticket_id INTEGER,
            action_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            amount REAL,
            payee TEXT,
            draft_message TEXT,
            requested_by TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_by TEXT,
            decided_at TEXT,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        )
    """)


def _approvals_table_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approval_requests'"
    ).fetchone() is not None


def _today(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise ValueError("The desk table has no date_today, so today's date is unknown.")
    return date.fromisoformat(row["date_today"])


def _one_month_before(d: date) -> date:
    year, month = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


@mcp.tool
def check_product(
    sku: str | None = None,
    name: str | None = None,
    size: str | None = None,
    quantity_needed: int | None = None,
) -> dict:
    """Check stock, location, and price for products (inventory + pricing).

    Find products by `sku` (e.g. "CC-TEE-WHITE") or part of the product `name`
    (e.g. "hoodie"); leave both empty to list every product. Pass `size`
    (S, M, L, XL, or OS) to check one size. Pass `quantity_needed` to see
    whether that many can be filled from stock and how many are short.

    `list_price` is the price to quote customers. `unit_cost` and margin are
    internal: use them only to judge discounts, never show them to shoppers.
    """
    where, params = [], []
    if sku:
        where.append("UPPER(i.sku) = UPPER(?)")
        params.append(sku.strip())
    if name:
        where.append("i.name LIKE ?")
        params.append(f"%{name.strip()}%")
    if size:
        where.append("UPPER(i.size) = UPPER(?)")
        params.append(size.strip())
    sql = """
        SELECT i.sku, i.name, i.size, i.qty, i.location,
               p.unit_cost, p.list_price
        FROM inventory i
        LEFT JOIN pricing p ON p.sku = i.sku
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY i.sku, CASE i.size WHEN 'XS' THEN 0 WHEN 'S' THEN 1 WHEN 'M' THEN 2 WHEN 'L' THEN 3 WHEN 'XL' THEN 4 WHEN 'XXL' THEN 5 ELSE 6 END"

    with _connect() as conn:
        today = _today(conn)
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        return {"today": today.isoformat(), "found": False,
                "message": "No product in inventory matches that SKU, name, and size."}

    products: dict[str, dict] = {}
    for r in rows:
        p = products.setdefault(r["sku"], {
            "sku": r["sku"],
            "name": r["name"],
            "list_price": r["list_price"],
            "unit_cost": r["unit_cost"],
            "margin_per_unit": (None if r["list_price"] is None or r["unit_cost"] is None
                                else round(r["list_price"] - r["unit_cost"], 2)),
            "sizes": [],
        })
        size_row = {"size": r["size"], "qty": r["qty"], "location": r["location"],
                    "in_stock": r["qty"] > 0}
        if quantity_needed is not None:
            size_row["can_fill"] = r["qty"] >= quantity_needed
            size_row["shortfall"] = max(quantity_needed - r["qty"], 0)
        p["sizes"].append(size_row)

    for p in products.values():
        p["total_qty"] = sum(s["qty"] for s in p["sizes"])
        if p["list_price"] is None:
            p["pricing_note"] = "No row in the pricing table for this SKU."

    result = {"today": today.isoformat(), "found": True, "products": list(products.values())}
    if quantity_needed is not None:
        result["quantity_needed"] = quantity_needed
    return result


@mcp.tool
def lookup_vendor(
    vendor_id: int | None = None,
    name: str | None = None,
    specialty: str | None = None,
) -> dict:
    """Look up vendors: who they are, what they supply, and their lead time.

    Filter by `vendor_id`, part of the vendor `name`, or part of the
    `specialty` (e.g. "reprint", "mugs", "courier"); leave all empty to list
    every vendor. `ready_if_ordered_today` is desk.date_today plus lead_days.
    """
    where, params = [], []
    if vendor_id is not None:
        where.append("id = ?")
        params.append(vendor_id)
    if name:
        where.append("name LIKE ?")
        params.append(f"%{name.strip()}%")
    if specialty:
        where.append("specialty LIKE ?")
        params.append(f"%{specialty.strip()}%")
    sql = "SELECT id, name, specialty, lead_days FROM vendors"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"

    with _connect() as conn:
        today = _today(conn)
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        return {"today": today.isoformat(), "found": False,
                "message": "No vendor matches that id, name, or specialty."}

    vendors = []
    for r in rows:
        v = dict(r)
        v["ready_if_ordered_today"] = date.fromordinal(today.toordinal() + r["lead_days"]).isoformat()
        vendors.append(v)
    return {"today": today.isoformat(), "found": True, "vendors": vendors}


@mcp.tool
def review_outgoing_payments(days_ahead: int = 30) -> dict:
    """Show what the shop has paid, what it still owes, and whether cash covers it.

    Cross-matches invoices, leases, payments, and cash_accounts:
    - An invoice is paid if its status is "paid" or a payment with
      kind "invoice" and ref_id = the invoice id exists.
    - Rent is paid for its next_due date if a payment with kind "rent" and
      ref_id = the lease id was made in the month before next_due or later.
    Unpaid items are listed if overdue or due within `days_ahead` days of
    desk.date_today. The cash check compares those against the total
    balance of all cash accounts.
    """
    with _connect() as conn:
        today = _today(conn)
        accounts = [dict(r) for r in conn.execute(
            "SELECT name, balance, date AS as_of FROM cash_accounts ORDER BY name")]
        payments = [dict(r) for r in conn.execute(
            "SELECT id, kind, ref_id, amount, account, paid_at, approved_by FROM payments ORDER BY paid_at")]
        invoices = conn.execute("""
            SELECT inv.id, inv.vendor_id, v.name AS vendor_name, inv.amount,
                   inv.due_date, inv.status, inv.description
            FROM invoices inv LEFT JOIN vendors v ON v.id = inv.vendor_id
            ORDER BY inv.due_date
        """).fetchall()
        leases = conn.execute("""
            SELECT id, space_name, landlord, monthly_rent, next_due, notes
            FROM leases ORDER BY next_due
        """).fetchall()

    def timing(due: date) -> dict:
        days = (due - today).days
        return {"days_until_due": days, "overdue": days < 0}

    paid, needed, later = [], [], []

    for inv in invoices:
        due = date.fromisoformat(inv["due_date"])
        match = [p for p in payments if (p["kind"] or "").lower() == "invoice" and p["ref_id"] == inv["id"]]
        item = {"kind": "invoice", "ref_id": inv["id"], "payee": inv["vendor_name"],
                "vendor_id": inv["vendor_id"], "description": inv["description"],
                "amount": inv["amount"], "due_date": inv["due_date"],
                "invoice_status": inv["status"], **timing(due)}
        if inv["status"].lower() == "paid" or match:
            item["payments"] = match
            paid.append(item)
        elif (due - today).days <= days_ahead:
            needed.append(item)
        else:
            later.append(item)

    for lease in leases:
        due = date.fromisoformat(lease["next_due"])
        cycle_start = _one_month_before(due)
        match = [p for p in payments
                 if (p["kind"] or "").lower() == "rent" and p["ref_id"] == lease["id"]
                 and date.fromisoformat(p["paid_at"][:10]) > cycle_start]
        item = {"kind": "rent", "ref_id": lease["id"], "payee": lease["landlord"],
                "description": f"Rent for {lease['space_name']}",
                "amount": lease["monthly_rent"], "due_date": lease["next_due"], **timing(due)}
        if match:
            item["payments"] = match
            paid.append(item)
        elif (due - today).days <= days_ahead:
            needed.append(item)
        else:
            later.append(item)

    needed.sort(key=lambda i: i["due_date"])
    cash = round(sum(a["balance"] for a in accounts), 2)
    owed = round(sum(i["amount"] for i in needed), 2)
    return {
        "today": today.isoformat(),
        "days_ahead": days_ahead,
        "cash_accounts": accounts,
        "total_cash": cash,
        "payments_made": paid,
        "payments_needed": needed,
        "total_needed": owed,
        "enough_cash_for_all": cash >= owed,
        "cash_left_after_paying_all": round(cash - owed, 2),
        "shortfall": round(max(owed - cash, 0), 2),
        "due_later": later,
        "payments_table_rows": len(payments),
    }


@mcp.tool
def get_tickets(ticket_id: int | None = None, status: str | None = None) -> dict:
    """Read tickets: the shop's work queue.

    Pass `ticket_id` for one ticket, or `status` (e.g. "open") to filter;
    leave both empty for every ticket. Each ticket's `sku`/`size`/`qty`,
    `lease_id`, and `invoice_id` point to the records needed to resolve it.
    """
    where, params = [], []
    if ticket_id is not None:
        where.append("id = ?")
        params.append(ticket_id)
    if status:
        where.append("LOWER(status) = LOWER(?)")
        params.append(status.strip())
    sql = "SELECT * FROM tickets"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at, id"
    with _connect() as conn:
        today = _today(conn)
        rows = [dict(r) for r in conn.execute(sql, params)]
    if not rows:
        return {"today": today.isoformat(), "found": False, "message": "No ticket matches that id or status."}
    return {"today": today.isoformat(), "found": True, "tickets": rows}


@mcp.tool
def get_lease(lease_id: int | None = None) -> dict:
    """Read the shop's lease(s): space, landlord, monthly rent, and next due date.

    Pass `lease_id` for one lease, or leave empty for all. `days_until_due`
    is counted from desk.date_today. Lease details are internal: never share
    them with customers.
    """
    sql = "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases"
    params: list = []
    if lease_id is not None:
        sql += " WHERE id = ?"
        params.append(lease_id)
    with _connect() as conn:
        today = _today(conn)
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    if not rows:
        return {"today": today.isoformat(), "found": False, "message": "No lease matches that id."}
    leases = []
    for r in rows:
        days = (date.fromisoformat(r["next_due"]) - today).days
        leases.append({**dict(r), "days_until_due": days, "overdue": days < 0})
    return {"today": today.isoformat(), "found": True, "leases": leases}


@mcp.tool
def check_discount(
    sku: str,
    quantity: int,
    discount_percent: float | None = None,
    offered_unit_price: float | None = None,
    size: str | None = None,
) -> dict:
    """Check the margin on a discounted sale (pricing + inventory).

    Give the `sku`, the `quantity`, and either `discount_percent` (e.g. 15) or
    `offered_unit_price`. Returns the discounted unit price, margin per unit
    and in total versus unit_cost, whether the price stays above cost, and
    the deepest discount that still covers cost. With `size`, it also says
    whether stock covers the quantity. This only checks numbers: any price
    override still needs human approval.
    """
    if (discount_percent is None) == (offered_unit_price is None):
        return {"ok": False, "message": "Give exactly one of discount_percent or offered_unit_price."}
    if quantity <= 0:
        return {"ok": False, "message": "quantity must be positive."}
    with _connect() as conn:
        today = _today(conn)
        price = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE UPPER(sku) = UPPER(?)", (sku.strip(),)
        ).fetchone()
        stock = None
        if size:
            stock = conn.execute(
                "SELECT size, qty FROM inventory WHERE UPPER(sku) = UPPER(?) AND UPPER(size) = UPPER(?)",
                (sku.strip(), size.strip()),
            ).fetchone()
    if price is None:
        return {"today": today.isoformat(), "ok": False, "message": f"No pricing row for SKU {sku}."}

    list_price, unit_cost = price["list_price"], price["unit_cost"]
    if discount_percent is not None:
        unit_price = round(list_price * (1 - discount_percent / 100), 2)
        pct = discount_percent
    else:
        unit_price = round(offered_unit_price, 2)
        pct = round((1 - unit_price / list_price) * 100, 2)
    margin = round(unit_price - unit_cost, 2)
    result = {
        "today": today.isoformat(),
        "ok": True,
        "sku": price["sku"],
        "quantity": quantity,
        "list_price": list_price,
        "unit_cost": unit_cost,
        "discount_percent": pct,
        "discounted_unit_price": unit_price,
        "margin_per_unit": margin,
        "total_revenue": round(unit_price * quantity, 2),
        "total_margin": round(margin * quantity, 2),
        "above_cost": margin > 0,
        "max_discount_percent_above_cost": round((1 - unit_cost / list_price) * 100, 2),
        "needs_human_approval": True,
    }
    if size:
        if stock is None:
            result["stock"] = {"size": size, "found": False}
        else:
            result["stock"] = {"size": stock["size"], "qty": stock["qty"],
                               "can_fill": stock["qty"] >= quantity,
                               "shortfall": max(quantity - stock["qty"], 0)}
    return result


@mcp.tool
def customer_safe_product_info(
    sku: str | None = None,
    name: str | None = None,
    size: str | None = None,
    quantity_needed: int | None = None,
) -> dict:
    """Product facts that are safe to tell a customer (inventory + pricing).

    Same lookup as check_product (by `sku` or part of `name`, optional
    `size`), but it returns only the product name, size, list price, and
    whether it's in stock (and, with `quantity_needed`, whether we can fill
    that amount). It never returns unit cost, margin, exact stock counts,
    aisle locations, or vendor details.
    """
    full = check_product(sku=sku, name=name, size=size, quantity_needed=quantity_needed)
    if not full.get("found"):
        return {"found": False, "message": "We couldn't find that product and size."}
    products = []
    for p in full["products"]:
        sizes = []
        for s in p["sizes"]:
            row = {"size": s["size"], "in_stock": s["in_stock"]}
            if quantity_needed is not None:
                row["can_fill_requested_quantity"] = s["can_fill"]
            sizes.append(row)
        products.append({"sku": p["sku"], "name": p["name"], "price": p["list_price"], "sizes": sizes})
    return {"found": True, "products": products}


@mcp.tool
def update_ticket(
    ticket_id: int,
    agent: str,
    status: TicketStatus | None = None,
    note: str | None = None,
) -> dict:
    """Record internal progress on a ticket (tickets table).

    Set `status` to open, in_progress, awaiting_approval, or blocked, and/or
    append a short `note` signed with the `agent` name. Agents can't close
    or resolve tickets: that is a human decision. This changes only
    Campus Customs' own records; it never contacts anyone.
    """
    if status is None and not note:
        return {"ok": False, "message": "Give a status, a note, or both."}
    with _connect_write() as conn:
        today = _today(conn)
        row = conn.execute("SELECT id, status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"ok": False, "message": f"No ticket {ticket_id}."}
        notes = row["notes"] or ""
        if note:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            notes = (notes + "\n" if notes else "") + f"[{today.isoformat()} {agent} @ {stamp}] {note.strip()}"
        new_status = status or row["status"]
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (new_status, notes, ticket_id))
    return {"ok": True, "ticket_id": ticket_id, "old_status": row["status"], "status": new_status, "notes": notes}


@mcp.tool
def request_human_approval(
    action_type: ApprovalAction,
    summary: str,
    requested_by: str,
    ticket_id: int | None = None,
    amount: float | None = None,
    payee: str | None = None,
    draft_message: str | None = None,
) -> dict:
    """Queue an action for a human to approve (approval_requests table). Nothing is executed.

    Use this for anything that leaves Campus Customs or commits money:
    paying an invoice or rent (`payment`), ordering from a vendor
    (`purchase_order`), sending a customer a message (`customer_message`,
    put the full draft in `draft_message`), or giving a discount
    (`price_override`). If the same ticket already has a pending request of
    the same type, that request is returned instead of a duplicate.
    """
    with _connect_write() as conn:
        today = _today(conn)
        _ensure_approvals_table(conn)
        if ticket_id is not None:
            if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
                return {"ok": False, "message": f"No ticket {ticket_id}."}
            existing = conn.execute(
                "SELECT * FROM approval_requests WHERE ticket_id = ? AND action_type = ? AND status = 'pending'",
                (ticket_id, action_type),
            ).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "request": dict(existing),
                        "message": "A pending request of this type already exists for this ticket."}
        cur = conn.execute(
            """INSERT INTO approval_requests
               (ticket_id, action_type, summary, amount, payee, draft_message, requested_by, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (ticket_id, action_type, summary.strip(), amount, payee, draft_message, requested_by,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        request = dict(conn.execute("SELECT * FROM approval_requests WHERE id = ?", (cur.lastrowid,)).fetchone())
    return {"ok": True, "duplicate": False, "today": today.isoformat(), "request": request,
            "message": "Queued for human approval. Nothing has been paid, ordered, or sent."}


@mcp.tool
def list_approval_requests(status: str | None = "pending", ticket_id: int | None = None) -> dict:
    """List actions waiting for (or decided by) a human (approval_requests table).

    Defaults to pending requests; pass `status=None` for all, or a
    `ticket_id` to see one ticket's requests.
    """
    with _connect() as conn:
        if not _approvals_table_exists(conn):
            return {"found": False, "requests": [], "message": "No approval requests yet."}
        where, params = [], []
        if status:
            where.append("status = ?")
            params.append(status)
        if ticket_id is not None:
            where.append("ticket_id = ?")
            params.append(ticket_id)
        sql = "SELECT * FROM approval_requests"
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY id", params)]
    return {"found": bool(rows), "requests": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs operations MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on port 8002 (8001 is the Lecture 9 server)",
    )
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=8002)
    else:
        mcp.run()
