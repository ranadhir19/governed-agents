"""Live agent registry.

The registry is the runtime source of truth: agents are registered here
explicitly (no invented agents), and every security contract is derived
deterministically from what is actually registered. ``snapshot()`` returns
the live view that contract derivation consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class Agent:
    """A registered agent and the attributes the risk rubric reads."""

    agent_id: str
    role: str
    # Data classes the agent may touch: "public", "internal", "pii", "pci", "phi"
    data_classes: frozenset
    # Tool scopes the agent is provisioned with, e.g. {"crm.read", "crm.write"}
    tool_scopes: frozenset
    # Hostnames the agent may legitimately send data to (governed back-ends)
    egress_allowlist: frozenset
    writes_production: bool = False
    external_egress: bool = False  # egress leaves the organisation boundary
    autonomous: bool = False  # multi-step execution without a human in the loop
    handles_secrets: bool = False
    status: str = "active"  # active | intake | quarantined

    def with_status(self, status: str) -> "Agent":
        from dataclasses import replace

        return replace(self, status=status)


class AgentRegistry:
    """Explicit, runtime registry of agents. Nothing is inferred."""

    def __init__(self) -> None:
        self._agents: Dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.agent_id in self._agents:
            raise ValueError(f"agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Agent:
        return self._agents[agent_id]

    def update(self, agent: Agent) -> None:
        if agent.agent_id not in self._agents:
            raise KeyError(f"unknown agent: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def set_status(self, agent_id: str, status: str) -> None:
        self.update(self.get(agent_id).with_status(status))

    def all(self) -> List[Agent]:
        return [self._agents[k] for k in sorted(self._agents)]

    def snapshot(self) -> List[dict]:
        """Live view consumed by contract derivation."""
        return [
            {
                "agent_id": a.agent_id,
                "role": a.role,
                "data_classes": sorted(a.data_classes),
                "tool_scopes": sorted(a.tool_scopes),
                "egress_allowlist": sorted(a.egress_allowlist),
                "writes_production": a.writes_production,
                "external_egress": a.external_egress,
                "autonomous": a.autonomous,
                "handles_secrets": a.handles_secrets,
                "status": a.status,
            }
            for a in self.all()
        ]

    def __len__(self) -> int:
        return len(self._agents)

    def __iter__(self) -> Iterable[Agent]:
        return iter(self.all())
