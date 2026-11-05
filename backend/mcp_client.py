"""Connects the agent team to the campus-customs-ops MCP server.

All shop facts reach the agents through this one MCP connection (stdio, launched from
mcp_server/server.py). Each agent sees only the tools its role needs.

Guardrail: before a customer_message draft is queued with request_human_approval, it is checked
for operations-side information (cost, margin, vendors, rent, other customers). The names to check
come from the MCP server itself (lookup_vendor, get_lease, get_tickets), not a second data layer.
"""

from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset

from backend.config import MCP_SERVER_SCRIPT
from backend.models import AgentName

AGENT_TOOLS: dict[AgentName, set[str]] = {
    "Boss": {"get_tickets", "update_ticket", "list_approval_requests"},
    "Inventory": {"get_tickets", "check_product", "lookup_vendor", "update_ticket"},
    "Accounting": {"get_tickets", "review_outgoing_payments", "check_discount", "check_product",
                   "lookup_vendor", "request_human_approval", "list_approval_requests", "update_ticket"},
    "Facilities": {"get_tickets", "get_lease", "review_outgoing_payments", "request_human_approval",
                   "list_approval_requests", "update_ticket"},
    "Customer Service": {"get_tickets", "customer_safe_product_info", "request_human_approval",
                         "list_approval_requests", "update_ticket"},
}

# Words that mean a customer message is leaking the operations side of the shop.
INTERNAL_TERMS = ["unit cost", "unit_cost", "our cost", "margin", "vendor", "supplier", "invoice",
                  "rent", "lease", "landlord", "cash balance", "bank balance", "checking account",
                  "purchase order", "wholesale"]


def _as_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {}
    return {}


async def _internal_names(call_tool: CallToolFunc, ticket_id: int | None) -> list[str]:
    """Vendor and landlord names, and requesters of other tickets, fetched over MCP."""
    names: list[str] = []
    vendors = _as_dict(await call_tool("lookup_vendor", {}))
    names += [v["name"] for v in vendors.get("vendors", [])]
    leases = _as_dict(await call_tool("get_lease", {}))
    names += [lease["landlord"] for lease in leases.get("leases", [])]
    tickets = _as_dict(await call_tool("get_tickets", {}))
    names += [t["requester"] for t in tickets.get("tickets", []) if t["id"] != ticket_id]
    return [n for n in names if n]


def leaked_terms(text: str, names: list[str]) -> list[str]:
    lowered = text.lower()
    hits = [t for t in INTERNAL_TERMS if re.search(rf"\b{re.escape(t)}\b", lowered)]
    hits += [n for n in names if n.lower() in lowered]
    return hits


async def _guard_tool_call(ctx: RunContext[Any], call_tool: CallToolFunc, name: str, args: dict[str, Any]) -> Any:
    if name == "request_human_approval" and args.get("action_type") == "customer_message":
        draft = args.get("draft_message") or ""
        if not draft.strip():
            raise ModelRetry("A customer_message approval request needs the full draft in draft_message.")
        hits = leaked_terms(draft, await _internal_names(call_tool, args.get("ticket_id")))
        if hits:
            raise ModelRetry(
                "This customer message reveals internal information "
                f"({', '.join(sorted(set(hits)))}). Rewrite it without costs, margins, vendors, rent, "
                "bills, or other customers, then queue it again."
            )
    return await call_tool(name, args)


@lru_cache(maxsize=1)
def shop_toolset() -> MCPToolset:
    """One stdio connection to the MCP server, shared by every agent in the process."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "CAMPUS_CUSTOMS_DB")}
    transport = PythonStdioTransport(MCP_SERVER_SCRIPT, env=env, cwd=str(MCP_SERVER_SCRIPT.parent),
                                     python_cmd=sys.executable)
    return MCPToolset(Client(transport), process_tool_call=_guard_tool_call, max_retries=2)


def toolset_for(agent: AgentName):
    allowed = AGENT_TOOLS[agent]
    return shop_toolset().filtered(lambda ctx, tool_def: tool_def.name in allowed)
