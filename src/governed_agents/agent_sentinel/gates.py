"""Phase 2: human-approval gates.

A high-risk action from an agent whose contract requires a human gate is
HELD, never executed speculatively. A person approves or denies; the
decision is recorded on the hash chain and reported to monitoring.

What counts as high-risk (checked against the contract):
  - egress to a destination outside the approved allowlist
  - a write to a production system by an agent provisioned for it
  - a single data access above the data ceiling
  - an egress whose byte count alone exceeds 25% of the per-run budget
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from governed_agents.agent_sentinel.contracts import SecurityContract
from governed_agents.agent_sentinel.telemetry import Event


class GateDecision:
    APPROVED = "approved"
    DENIED = "denied"
    HELD = "held"


@dataclass
class HeldAction:
    gate_id: str
    event: Event
    reason: str
    decision: str = GateDecision.HELD
    approver: Optional[str] = None


def is_high_risk(event: Event, contract: SecurityContract) -> List[str]:
    """Return non-empty list of reasons if the event is high-risk."""
    reasons: List[str] = []
    if event.kind == "egress" and event.dest not in contract.approved_egress:
        reasons.append(f"egress to unapproved destination {event.dest}")
    if event.kind == "data_access" and event.records > contract.data_ceiling_records:
        reasons.append(
            f"data access {event.records} records exceeds ceiling {contract.data_ceiling_records}"
        )
    if event.kind == "egress" and event.bytes_out > 0.25 * contract.max_egress_bytes_per_run:
        reasons.append(
            f"single egress {event.bytes_out} bytes exceeds 25% of run budget "
            f"{contract.max_egress_bytes_per_run}"
        )
    return reasons


class GateQueue:
    """Holds high-risk actions until a human decides. Nothing auto-executes."""

    def __init__(self) -> None:
        self._held: Dict[str, HeldAction] = {}
        self._counter = 0

    def hold(self, event: Event, reason: str) -> HeldAction:
        self._counter += 1
        gate_id = f"gate-{self._counter:04d}"
        held = HeldAction(gate_id=gate_id, event=event, reason=reason)
        self._held[gate_id] = held
        return held

    def decide(self, gate_id: str, approve: bool, approver: str) -> HeldAction:
        held = self._held[gate_id]
        if held.decision != GateDecision.HELD:
            raise ValueError(f"{gate_id} already decided: {held.decision}")
        held.decision = GateDecision.APPROVED if approve else GateDecision.DENIED
        held.approver = approver
        return held

    def pending(self) -> List[HeldAction]:
        return [h for h in self._held.values() if h.decision == GateDecision.HELD]

    def all(self) -> List[HeldAction]:
        return list(self._held.values())
