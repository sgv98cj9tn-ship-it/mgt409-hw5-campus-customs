"""The Campus Customs agent team: Boss, Inventory, Accounting, Facilities, Customer Service.

- Each agent is a PydanticAI Agent with its own prompt (backend/prompts/<agent>.md), its own
  slice of MCP tools (backend/mcp_client.py), and one extra tool, `delegate`, so any agent can
  hand work to any other agent (full connectivity).
- Delegation guards: no delegating to yourself or to an agent already in the chain (no loops),
  at most MAX_DELEGATION_DEPTH levels and MAX_DELEGATIONS_PER_TICKET hand-offs per ticket.
- Every agent in a ticket run shares one usage counter, so TICKET_USAGE_LIMITS caps the whole run.
- run_agent() drives the agent loop with Agent.iter() and appends every step to the audit trail.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import RunUsage

from backend import audit
from backend.config import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_OUTPUT_TOKENS,
    PROMPTS_DIR,
    REASONING_EFFORT,
    TICKET_USAGE_LIMITS,
    build_model,
)
from backend.mcp_client import toolset_for
from backend.models import AgentName, Delegation, RunState, SpecialistReport, TeamDeps, TicketPlan

AGENT_NAMES: tuple[AgentName, ...] = ("Boss", "Inventory", "Accounting", "Facilities", "Customer Service")
PROMPT_FILES: dict[AgentName, str] = {
    "Boss": "boss.md",
    "Inventory": "inventory.md",
    "Accounting": "accounting.md",
    "Facilities": "facilities.md",
    "Customer Service": "customer_service.md",
}


async def delegate(ctx: RunContext[TeamDeps], to_agent: AgentName, task: str) -> dict[str, Any]:
    """Hand a focused task to another Campus Customs agent and get its report back.

    Args:
        to_agent: Boss, Inventory, Accounting, Facilities, or Customer Service.
        task: What you need from them, with the ticket id and the facts they need
            (SKU, size, quantity, invoice or lease id). Be specific about the question.

    Returns the other agent's report (summary, facts, flags, proposed actions), or a refusal
    explaining why the hand-off wasn't allowed.
    """
    deps = ctx.deps
    state = deps.state

    def refuse(reason: str) -> dict[str, Any]:
        record = Delegation(from_agent=deps.agent, to_agent=to_agent, task=task, depth=deps.depth + 1,
                            status="refused", reply=reason)
        state.delegations.append(record)
        audit.record("delegation_refused", run_id=state.run_id, ticket_id=state.ticket_id, agent=deps.agent,
                     depth=deps.depth, to_agent=to_agent, task=task, reason=reason)
        return {"status": "refused", "reason": reason}

    if to_agent == deps.agent:
        return refuse("You can't delegate to yourself. Do the work with your own tools.")
    if to_agent in deps.chain:
        return refuse(f"{to_agent} is already working on this request higher up the chain "
                      f"({' -> '.join(deps.chain)}). Return what you have instead of looping back.")
    if deps.depth + 1 > MAX_DELEGATION_DEPTH:
        return refuse("Delegation depth limit reached. Answer with what you have.")
    if len(state.delegations) >= MAX_DELEGATIONS_PER_TICKET:
        return refuse("This ticket has used all of its delegations. Answer with what you have.")

    child = TeamDeps(agent=to_agent, chain=(*deps.chain, to_agent), state=state)
    audit.record("delegation_started", run_id=state.run_id, ticket_id=state.ticket_id, agent=deps.agent,
                 depth=deps.depth, to_agent=to_agent, task=task)
    try:
        report = await run_agent(to_agent, task, child, usage=ctx.usage)
        reply = report.model_dump()
        status = "done"
    except Exception as exc:  # noqa: BLE001 - the caller gets the error and can carry on
        if type(exc).__name__ == "UsageLimitExceeded":
            raise
        reply = f"{type(exc).__name__}: {str(exc)[:300]}"
        status = "error"
    state.delegations.append(Delegation(from_agent=deps.agent, to_agent=to_agent, task=task,
                                        depth=child.depth, status=status, reply=reply))
    audit.record("delegation_finished", run_id=state.run_id, ticket_id=state.ticket_id, agent=deps.agent,
                 depth=deps.depth, to_agent=to_agent, status=status)
    return {"status": status, "agent": to_agent, "report": reply}


def _instructions(name: AgentName) -> str:
    return (PROMPTS_DIR / PROMPT_FILES[name]).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def build_agent(name: AgentName) -> Agent[TeamDeps, Any]:
    return Agent(
        build_model(),
        name=name,
        deps_type=TeamDeps,
        output_type=TicketPlan if name == "Boss" else SpecialistReport,
        instructions=_instructions(name),
        tools=[delegate],
        toolsets=[toolset_for(name)],
        model_settings={"max_tokens": MAX_OUTPUT_TOKENS,
                        **({"openai_reasoning_effort": REASONING_EFFORT[name]} if name in REASONING_EFFORT else {})},
        retries=2,
    )


async def run_agent(name: AgentName, task: str, deps: TeamDeps, usage: RunUsage | None = None) -> Any:
    """Run one agent's loop, appending every step to the audit trail. Returns its output."""
    state = deps.state
    agent = build_agent(name)
    common = {"run_id": state.run_id, "ticket_id": state.ticket_id, "agent": name, "depth": deps.depth}
    audit.record("agent_started", **common, chain=list(deps.chain), task=task)
    step = 0
    try:
        async with agent.iter(task, deps=deps, usage=usage, usage_limits=TICKET_USAGE_LIMITS) as run:
            async for node in run:
                step += 1
                if Agent.is_model_request_node(node):
                    audit.record("model_request", **common, step=step, parts=audit.message_parts(node.request))
                elif Agent.is_call_tools_node(node):
                    audit.record("model_response", **common, step=step,
                                 parts=audit.message_parts(node.model_response),
                                 usage=run.usage.__dict__ if hasattr(run.usage, "__dict__") else str(run.usage))
                elif Agent.is_end_node(node):
                    audit.record("agent_finished", **common, step=step,
                                 output=node.data.output.model_dump(),
                                 usage=run.usage.__dict__ if hasattr(run.usage, "__dict__") else str(run.usage))
            return run.result.output
    except Exception as exc:
        audit.record("agent_error", **common, step=step, error=f"{type(exc).__name__}: {str(exc)[:500]}")
        raise


async def run_ticket(ticket_id: int) -> dict[str, Any]:
    """The Boss works one ticket end to end. Returns the plan, the hand-offs, and token usage."""
    state = RunState(run_id=uuid.uuid4().hex[:12], ticket_id=ticket_id)
    deps = TeamDeps(agent="Boss", chain=("Boss",), state=state)
    usage = RunUsage()
    task = (f"Work ticket {ticket_id}. Read it with get_tickets, decide which agents should handle it, "
            "delegate to them, record progress with update_ticket, and return the ticket plan.")
    plan = await run_agent("Boss", task, deps, usage=usage)
    return {
        "run_id": state.run_id,
        "ticket_id": ticket_id,
        "plan": plan.model_dump(),
        "delegations": [d.model_dump() for d in state.delegations],
        "usage": {"requests": usage.requests, "tool_calls": usage.tool_calls,
                  "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
    }
