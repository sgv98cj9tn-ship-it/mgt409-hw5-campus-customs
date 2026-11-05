"""Run the agent team on tickets from the command line.

From the Homework 5 folder:
    .venv/bin/python -m backend.run_tickets 101            # one ticket
    .venv/bin/python -m backend.run_tickets --all-open     # every open ticket
Options:
    --db PATH      point the MCP server at another copy of the database (e.g. a test copy)
    --audit PATH   write the audit trail somewhere else (default output/audit_trail.json)
    --out PATH     also save the results as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team on tickets")
    parser.add_argument("ticket_ids", nargs="*", type=int)
    parser.add_argument("--all-open", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--audit")
    parser.add_argument("--out")
    args = parser.parse_args()
    if not args.ticket_ids and not args.all_open:
        parser.error("Give ticket ids or --all-open.")

    # Set before the backend modules read their configuration.
    if args.db:
        os.environ["CAMPUS_CUSTOMS_DB"] = str(Path(args.db).resolve())
    if args.audit:
        os.environ["AUDIT_TRAIL_PATH"] = str(Path(args.audit).resolve())

    from backend.agents import run_ticket
    from backend.mcp_client import shop_toolset

    async def run() -> list[dict]:
        results = []
        async with shop_toolset():  # one MCP connection for the whole run
            ids = list(args.ticket_ids)
            if args.all_open:
                tickets = await shop_toolset().direct_call_tool("get_tickets", {"status": "open"})
                ids += [t["id"] for t in tickets.get("tickets", []) if t["id"] not in ids]
            for ticket_id in ids:
                print(f"\n=== Ticket {ticket_id} ===")
                result = await run_ticket(ticket_id)
                print(json.dumps(result["plan"], indent=2))
                print("usage:", result["usage"])
                results.append(result)
        return results

    results = asyncio.run(run())
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
