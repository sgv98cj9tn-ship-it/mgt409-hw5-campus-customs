"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["Boss", "Inventory", "Accounting", "Facilities", "Customer Service"]
TicketStatus = Literal["open", "in_progress", "awaiting_approval", "blocked"]
ApprovalAction = Literal["payment", "purchase_order", "customer_message", "price_override", "other"]


class Fact(BaseModel):
    """One fact an agent relied on, with the MCP tool it came from."""

    label: str = Field(description="What the fact is, e.g. 'CC-TEE-WHITE size S stock'.")
    value: str = Field(description="The value exactly as the tool returned it.")
    source_tool: str = Field(description="The MCP tool that returned it.")


class ProposedAction(BaseModel):
    """Something that should happen next on the ticket."""

    action: str = Field(description="What should be done, in one sentence.")
    owner: AgentName | Literal["Human"] = Field(description="Who should do it.")
    needs_human_approval: bool = Field(description="True for anything that spends money or leaves Campus Customs.")
    approval_request_id: int | None = Field(default=None, description="The approval_requests id, if one was queued.")


class SpecialistReport(BaseModel):
    """What Inventory, Accounting, Facilities, or Customer Service returns."""

    agent: AgentName
    summary: str = Field(description="Two to four sentences: what you found and what you recommend.")
    facts: list[Fact] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list, description="Shortfalls, overdue items, risks, rule conflicts.")
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    customer_message_draft: str | None = Field(
        default=None, description="Customer Service only: the draft message, safe to show the customer."
    )


class PlanStep(BaseModel):
    order: int
    agent: AgentName | Literal["Human"]
    action: str
    needs_human_approval: bool
    status: Literal["done", "waiting_on_human", "blocked", "to_do"]


class TicketPlan(BaseModel):
    """What the Boss returns for one ticket."""

    ticket_id: int
    ticket_type: str
    assigned_agents: list[AgentName]
    summary: str = Field(description="Three to five sentences a manager can act on.")
    steps: list[PlanStep]
    blockers: list[str] = Field(default_factory=list)
    approval_request_ids: list[int] = Field(default_factory=list)
    customer_message_draft: str | None = None
    ticket_status: TicketStatus


class Delegation(BaseModel):
    """One hand-off between agents, kept for the audit trail and the final result."""

    from_agent: AgentName
    to_agent: AgentName
    task: str
    depth: int
    status: Literal["done", "refused", "error"]
    reply: dict[str, Any] | str | None = None


@dataclass
class RunState:
    """Shared by every agent working on one ticket."""

    run_id: str
    ticket_id: int | None
    delegations: list[Delegation] = field(default_factory=list)


@dataclass
class TeamDeps:
    """Per-agent run dependencies: who is running, and the chain of agents that led here."""

    agent: AgentName
    chain: tuple[AgentName, ...]
    state: RunState

    @property
    def depth(self) -> int:
        return len(self.chain) - 1
