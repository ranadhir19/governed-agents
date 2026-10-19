"""Phase 3: containment. Never silent, never irreversible.

Trigger: honeytoken tripwires, or a per-agent circuit breaker that trips
after 2 critical findings inside a rolling window.

Response: a model-independent network kill-switch (egress blocked at the
adapter layer regardless of which model produced the action) plus
quarantine (the agent takes no new actions). Containment is applied ONLY
on human confirmation, is stored persistently, is reported to platform
monitoring as a self-healing action, and is releasable by a human.

Every transition emits a monitoring event and a hash-chain incident
record, so containment can never happen quietly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from governed_agents.agent_sentinel.scorer import Finding
from governed_agents.agent_sentinel.chain import HashChain
from governed_agents.agent_sentinel.monitoring import MonitoringBus


@dataclass
class ContainmentState:
    agent_id: str
    contained: bool = False
    kill_switch_on: bool = False
    quarantined: bool = False
    incident_id: Optional[str] = None
    confirmed_by: Optional[str] = None
    released_by: Optional[str] = None


class CircuitBreaker:
    """Trips when an agent accumulates >= threshold critical findings in window."""

    def __init__(self, threshold: int = 2, window_seconds: float = 600.0) -> None:
        self.threshold = threshold
        self.window = window_seconds
        self._criticals: Dict[str, List[float]] = {}
        self._tripped: Dict[str, bool] = {}

    def observe(self, finding: Finding, ts: float) -> bool:
        """Feed a finding; return True if this observation trips the breaker."""
        if finding.severity != "critical":
            return False
        hist = self._criticals.setdefault(finding.agent_id, [])
        hist.append(ts)
        hist[:] = [t for t in hist if ts - t <= self.window]
        if len(hist) >= self.threshold and not self._tripped.get(finding.agent_id):
            self._tripped[finding.agent_id] = True
            return True
        return False

    def tripped(self, agent_id: str) -> bool:
        return self._tripped.get(agent_id, False)

    def reset(self, agent_id: str) -> None:
        self._tripped[agent_id] = False
        self._criticals[agent_id] = []


class ContainmentController:
    """Human-confirmed, reversible containment with persistent state."""

    def __init__(
        self,
        chain: HashChain,
        monitoring: MonitoringBus,
        state_path: str,
    ) -> None:
        self.chain = chain
        self.monitoring = monitoring
        self.state_path = state_path
        self._states: Dict[str, ContainmentState] = {}
        self._incident_counter = 0
        self._load()

    # -- persistence -----------------------------------------------------
    def _load(self) -> None:
        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                raw = json.load(f)
            for agent_id, s in raw.get("states", {}).items():
                self._states[agent_id] = ContainmentState(agent_id=agent_id, **s)
            self._incident_counter = raw.get("incident_counter", 0)

    def _save(self) -> None:
        raw = {
            "incident_counter": self._incident_counter,
            "states": {
                aid: {
                    "contained": s.contained,
                    "kill_switch_on": s.kill_switch_on,
                    "quarantined": s.quarantined,
                    "incident_id": s.incident_id,
                    "confirmed_by": s.confirmed_by,
                    "released_by": s.released_by,
                }
                for aid, s in self._states.items()
            },
        }
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(raw, f, indent=2)

    # -- queries ----------------------------------------------------------
    def state(self, agent_id: str) -> ContainmentState:
        return self._states.setdefault(agent_id, ContainmentState(agent_id=agent_id))

    def egress_blocked(self, agent_id: str) -> bool:
        return self.state(agent_id).kill_switch_on

    def actions_blocked(self, agent_id: str) -> bool:
        return self.state(agent_id).quarantined

    # -- transitions (human confirmation required) -------------------------
    def propose(self, agent_id: str, trigger: str, ts: float) -> str:
        """Open a tamper-evident incident record. Returns the incident id."""
        self._incident_counter += 1
        incident_id = f"INC-{self._incident_counter:04d}"
        self.chain.append("incident", {
            "incident_id": incident_id,
            "agent_id": agent_id,
            "trigger": trigger,
            "status": "proposed",
        }, ts)
        self.monitoring.emit(
            "self_healing", f"containment proposed for {agent_id} ({trigger})",
            ts, incident_id=incident_id, agent_id=agent_id, trigger=trigger,
        )
        return incident_id

    def confirm(self, agent_id: str, incident_id: str, approver: str, ts: float) -> ContainmentState:
        """Human-confirmed containment: kill-switch ON, agent quarantined."""
        st = self.state(agent_id)
        if st.contained:
            raise ValueError(f"{agent_id} is already contained")
        st.contained = True
        st.kill_switch_on = True
        st.quarantined = True
        st.incident_id = incident_id
        st.confirmed_by = approver
        st.released_by = None
        self._save()
        self.chain.append("incident", {
            "incident_id": incident_id,
            "agent_id": agent_id,
            "status": "contained",
            "confirmed_by": approver,
            "effects": ["network kill-switch on", "agent quarantined"],
        }, ts)
        self.monitoring.emit(
            "self_healing",
            f"containment CONFIRMED for {agent_id}: kill-switch on, quarantined",
            ts, incident_id=incident_id, agent_id=agent_id, confirmed_by=approver,
        )
        return st

    def release(self, agent_id: str, approver: str, ts: float) -> ContainmentState:
        """Human-approved release. Containment is always reversible."""
        st = self.state(agent_id)
        if not st.contained:
            raise ValueError(f"{agent_id} is not contained")
        st.contained = False
        st.kill_switch_on = False
        st.quarantined = False
        st.released_by = approver
        self._save()
        self.chain.append("incident", {
            "incident_id": st.incident_id,
            "agent_id": agent_id,
            "status": "released",
            "released_by": approver,
        }, ts)
        self.monitoring.emit(
            "self_healing", f"containment RELEASED for {agent_id}",
            ts, incident_id=st.incident_id, agent_id=agent_id, released_by=approver,
        )
        return st
