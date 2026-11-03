"""Phase 0: runtime security contracts derived from the live registry.

The risk-tiering rubric is transparent and deterministic: every point has
a named reason. Tiers: low / moderate / high / critical.

Rubric (points):
  +2  touches pci or phi data
  +1  touches pii data (non-pci/phi)
  +1  writes to production systems
  +1  egress leaves the organisation boundary
  +1  autonomous multi-step execution without a human in the loop
  +1  handles secrets / credentials

Tier mapping: 0 -> low, 1-2 -> moderate, 3 -> high, >=4 -> critical.

Each contract states: approved egress (governed back-ends only), allowed
tool scopes, a data ceiling (sensitive records per run), per-run action
and egress-byte budgets that tighten with risk, whether a human gate is
required (high / critical), and planted honeytokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from governed_agents.agent_sentinel.registry import Agent

RUBRIC: Tuple[Tuple[str, int], ...] = (
    ("touches pci/phi data", 2),
    ("touches pii data", 1),
    ("writes to production", 1),
    ("external egress", 1),
    ("autonomous multi-step execution", 1),
    ("handles secrets", 1),
)

# Per-run budgets tighten with risk: (max_actions, max_egress_bytes, data_ceiling_records)
_BUDGETS: Dict[str, Tuple[int, int, int]] = {
    "low": (200, 50 * 1024 * 1024, 10_000),
    "moderate": (100, 10 * 1024 * 1024, 1_000),
    "high": (50, 2 * 1024 * 1024, 100),
    "critical": (20, 512 * 1024, 10),
}


def score_agent(agent: Agent) -> Tuple[int, List[str]]:
    """Return (risk_score, reasons). Deterministic; no randomness."""
    score = 0
    reasons: List[str] = []
    data = set(agent.data_classes)
    if data & {"pci", "phi"}:
        score += 2
        reasons.append("touches pci/phi data (+2)")
    elif "pii" in data:
        score += 1
        reasons.append("touches pii data (+1)")
    if agent.writes_production:
        score += 1
        reasons.append("writes to production (+1)")
    if agent.external_egress:
        score += 1
        reasons.append("external egress (+1)")
    if agent.autonomous:
        score += 1
        reasons.append("autonomous multi-step execution (+1)")
    if agent.handles_secrets:
        score += 1
        reasons.append("handles secrets (+1)")
    return score, reasons


def risk_tier(score: int) -> str:
    if score <= 0:
        return "low"
    if score <= 2:
        return "moderate"
    if score == 3:
        return "high"
    return "critical"


@dataclass(frozen=True)
class SecurityContract:
    agent_id: str
    risk_tier: str
    risk_score: int
    rubric_reasons: Tuple[str, ...]
    approved_egress: frozenset
    allowed_tool_scopes: frozenset
    data_ceiling_records: int
    max_actions_per_run: int
    max_egress_bytes_per_run: int
    human_gate_required: bool
    honeytokens: Tuple[str, ...]


def _honeytokens_for(agent: Agent, tier: str) -> Tuple[str, ...]:
    """Plant honeytokens in every agent that touches non-public data."""
    data = set(agent.data_classes)
    if data <= {"public"}:
        return ()
    tokens = [f"honey-customer-{agent.agent_id}"]
    if data & {"pci", "phi", "pii"} or agent.handles_secrets:
        tokens.append(f"honey-apikey-{agent.agent_id}")
    return tuple(tokens)


def derive_contract(agent: Agent) -> SecurityContract:
    """Deterministically derive the runtime security contract."""
    score, reasons = score_agent(agent)
    tier = risk_tier(score)
    max_actions, max_bytes, ceiling = _BUDGETS[tier]
    return SecurityContract(
        agent_id=agent.agent_id,
        risk_tier=tier,
        risk_score=score,
        rubric_reasons=tuple(reasons),
        approved_egress=frozenset(agent.egress_allowlist),
        allowed_tool_scopes=frozenset(agent.tool_scopes),
        data_ceiling_records=ceiling,
        max_actions_per_run=max_actions,
        max_egress_bytes_per_run=max_bytes,
        human_gate_required=tier in ("high", "critical"),
        honeytokens=_honeytokens_for(agent, tier),
    )


def derive_all(agents: List[Agent]) -> Dict[str, SecurityContract]:
    return {a.agent_id: derive_contract(a) for a in agents}
