"""Write output/resolved_tickets.json from the working database and the audit trail.

For each ticket: id, final status, a short outcome (the Boss's plan summary from the latest
run), what each agent contributed in that run, and every human decision (payments approved,
customer messages sent). Only runs after the most recent database reset count, so a fresh
start doesn't mix in older test runs.

Called by backend/main.py after every run, approval, send, and reset, and runnable by hand:
    .venv/bin/python -m backend.resolved_export
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.config import AUDIT_TRAIL_PATH, DB_PATH, PROJECT_DIR

RESOLVED_PATH = PROJECT_DIR / "output" / "resolved_tickets.json"

# One-line outcomes for the final Problem 9 runs, keyed by run id so they only apply to those
# runs. Any later run falls back to the Boss's own plan summary.
SHORT_OUTCOMES = {
    "f2e09d3ec4a8": "Size S is sold out. A human paid the overdue $840 invoice 501 and sent a reply saying we're checking "
                    "availability; the restock still needs a purchase order, so nothing was promised.",
    "b49f3ac5a7f1": "The rent notice matched lease 1 ($2,400 due 2026-09-02). A human paid the rent, leaving $160 in checking.",
    "62255fcd7a4d": "Only 8 of 20 hoodies are in stock. A human approved a 15% discount ($49.30 a unit, above the $22 cost) and "
                    "sent a reply that promises neither the full order nor a date. No cash moved.",
}
HIDDEN_TOOLS = {"final_result", "delegate"}


def _events_since_reset() -> list[dict[str, Any]]:
    if not AUDIT_TRAIL_PATH.exists():
        return []
    events = []
    with AUDIT_TRAIL_PATH.open(encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "db_reset":
                events = []  # start over at each reset
                continue
            events.append(e)
    return events


def _runs_for(events: list[dict[str, Any]], ticket_id: int) -> list[dict[str, Any]]:
    """Each Boss run of this ticket, oldest first, with how it ended and what each agent did."""
    run_ids: list[str] = []
    for e in events:
        if e.get("ticket_id") == ticket_id and e.get("event") == "agent_started" and e.get("depth") == 0:
            run_ids.append(e["run_id"])
    runs = []
    for run_id in run_ids:
        mine = [e for e in events if e.get("run_id") == run_id]
        agents: dict[str, dict[str, Any]] = {}

        def get(name: str) -> dict[str, Any]:
            return agents.setdefault(name, {"agent": name, "summary": None, "tools_used": [],
                                            "handed_off_to": [], "flags": []})

        plan, error = None, None
        for e in mine:
            name = e.get("agent")
            if e["event"] == "agent_started":
                get(name)
            elif e["event"] == "model_response":
                for p in e.get("parts", []):
                    if p.get("kind") == "tool_call" and p.get("tool") not in HIDDEN_TOOLS:
                        tools = get(name)["tools_used"]
                        if p["tool"] not in tools:
                            tools.append(p["tool"])
            elif e["event"] == "delegation_started":
                hand = get(name)["handed_off_to"]
                if e.get("to_agent") not in hand:
                    hand.append(e.get("to_agent"))
            elif e["event"] == "agent_finished":
                out = e.get("output") or {}
                a = get(name)
                a["summary"] = out.get("summary")
                a["flags"] = out.get("flags") or out.get("blockers") or []
                if e.get("depth") == 0:
                    plan = out
            elif e["event"] == "agent_error" and e.get("depth") == 0:
                error = e.get("error")
        runs.append({
            "run_id": run_id,
            "started": mine[0]["ts"] if mine else None,
            "finished": plan is not None,
            "error": error,
            "boss_plan": plan,
            "agents": list(agents.values()),
        })
    return runs


def build() -> dict[str, Any]:
    events = _events_since_reset()
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tickets = [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY id")]
        has_approvals = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approval_requests'").fetchone() is not None
        approvals = [dict(r) for r in conn.execute("SELECT * FROM approval_requests ORDER BY id")] if has_approvals else []
        payments = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY id")]
        checking = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()
        today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()[0]
    finally:
        conn.close()

    sent = {e.get("approval_id"): e for e in events if e.get("event") == "customer_message_sent"}
    out_tickets = []
    for t in tickets:
        runs = _runs_for(events, t["id"])
        latest = next((r for r in reversed(runs) if r["finished"]), runs[-1] if runs else None)
        human = []
        for a in (x for x in approvals if x["ticket_id"] == t["id"]):
            item = {"approval_id": a["id"], "action_type": a["action_type"], "requested_by": a["requested_by"],
                    "status": a["status"], "decided_by": a.get("decided_by"), "decided_at": a.get("decided_at"),
                    "summary": a["summary"]}
            if a["action_type"] in ("payment", "purchase_order"):
                item.update(amount=a["amount"], payee=a["payee"])
            if a["action_type"] == "customer_message":
                s = sent.get(a["id"], {})
                item.update(agent_draft=a["draft_message"], sent_message=a.get("final_message"),
                            edited_by_human=s.get("edited"), recipient=s.get("recipient", t["requester"]),
                            delivery="simulated: marked sent on the board, no email or message actually went out"
                            if a["status"] == "sent" else None)
            human.append(item)
        plan = (latest or {}).get("boss_plan") or {}
        out_tickets.append({
            "id": t["id"],
            "type": t["type"],
            "requester": t["requester"],
            "subject": t["subject"],
            "final_status": t["status"],
            "outcome": SHORT_OUTCOMES.get((latest or {}).get("run_id")) or plan.get("summary")
                       or ("The last run ended with an error before the Boss's plan." if runs else "Not run yet."),
            "boss_plan_summary": plan.get("summary"),
            "agents": (latest or {}).get("agents", []),
            "human_approvals": human,
            "runs": [{"run_id": r["run_id"], "started": r["started"], "finished": r["finished"], "error": r["error"]}
                     for r in runs],
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "desk_date": today,
        "checking_balance": round(checking[0], 2) if checking else None,
        "payments": payments,
        "tickets": out_tickets,
    }


def write() -> None:
    RESOLVED_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESOLVED_PATH.write_text(json.dumps(build(), indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
    print(f"Wrote {RESOLVED_PATH}")
