"""Phase 1b: detect-only scoring of events against contract + baseline.

Findings:
  critical: honeytoken tripwire, self-exfiltration, new egress destination
  high:     out-of-scope tool, egress volume spike, prompt injection,
            data-ceiling breach, per-run budget breach

Every finding maps to the public MITRE ATLAS taxonomy (tactic + technique
name) and to the OWASP Top 10 for LLM Applications (2025). The mapping is
best-effort and documented in the README; ATLAS technique names are used
where the taxonomy defines them, otherwise the ATLAS tactic is given.

Phase 1 action is ALWAYS detect_only: the scorer never blocks, holds, or
contains. Gating (phase 2) and containment (phase 3) are separate,
human-in-the-loop mechanisms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from governed_agents.agent_sentinel.contracts import SecurityContract
from governed_agents.agent_sentinel.baselines import Baseline
from governed_agents.agent_sentinel.telemetry import Event

# finding_type -> (severity, atlas_tactic, atlas_technique, owasp_id, owasp_name)
FINDING_CATALOG: Dict[str, Tuple[str, str, str, str, str]] = {
    "honeytoken_tripwire": (
        "critical", "Exfiltration", "Exfiltration via Cyber Means",
        "LLM02", "Sensitive Information Disclosure",
    ),
    "self_exfiltration": (
        "critical", "Exfiltration", "Exfiltration via Cyber Means",
        "LLM02", "Sensitive Information Disclosure",
    ),
    "new_egress": (
        "critical", "Exfiltration", "Exfiltration via Cyber Means",
        "LLM06", "Excessive Agency",
    ),
    "out_of_scope_tool": (
        "high", "Execution", "Execution (tactic-level mapping)",
        "LLM06", "Excessive Agency",
    ),
    "volume_spike": (
        "high", "Exfiltration", "Exfiltration via Cyber Means",
        "LLM10", "Unbounded Consumption",
    ),
    "prompt_injection": (
        "high", "Initial Access", "LLM Prompt Injection",
        "LLM01", "Prompt Injection",
    ),
    "data_ceiling_breach": (
        "high", "Collection", "Collection (tactic-level mapping)",
        "LLM10", "Unbounded Consumption",
    ),
    "run_budget_breach": (
        "high", "Execution", "Execution (tactic-level mapping)",
        "LLM10", "Unbounded Consumption",
    ),
}

_SENSITIVE = {"pii", "pci", "phi"}


@dataclass(frozen=True)
class Finding:
    finding_type: str
    severity: str
    agent_id: str
    event_seq: int
    run_id: str
    atlas_tactic: str
    atlas_technique: str
    owasp_id: str
    owasp_name: str
    detail: str
    action: str = "detect_only"


def _make(finding_type: str, event: Event, detail: str) -> Finding:
    sev, tactic, technique, owasp_id, owasp_name = FINDING_CATALOG[finding_type]
    return Finding(
        finding_type=finding_type,
        severity=sev,
        agent_id=event.agent_id,
        event_seq=event.seq,
        run_id=event.run_id,
        atlas_tactic=tactic,
        atlas_technique=technique,
        owasp_id=owasp_id,
        owasp_name=owasp_name,
        detail=detail,
    )


class Scorer:
    """Stateful detect-only scorer with per-run budget accumulators."""

    def __init__(
        self,
        contracts: Dict[str, SecurityContract],
        baselines: Dict[str, Baseline],
        spike_sigma: float = 4.0,
        spike_floor_bytes: int = 1_000_000,
    ) -> None:
        self.contracts = contracts
        self.baselines = baselines
        self.spike_sigma = spike_sigma
        self.spike_floor_bytes = spike_floor_bytes
        # run_id -> {"actions": int, "bytes": int}
        self._runs: Dict[str, Dict[str, int]] = {}

    def _run_usage(self, run_id: str) -> Dict[str, int]:
        return self._runs.setdefault(run_id, {"actions": 0, "bytes": 0})

    def score(self, event: Event) -> List[Finding]:
        contract = self.contracts[event.agent_id]
        baseline = self.baselines.get(event.agent_id)
        findings: List[Finding] = []

        usage = self._run_usage(event.run_id)
        usage["actions"] += 1
        usage["bytes"] += event.bytes_out

        markers = set(event.payload_markers)

        # --- critical: honeytoken tripwire ---------------------------------
        honey_hits = [m for m in markers if m.startswith("honeytoken:")]
        if honey_hits and event.kind == "egress":
            token = honey_hits[0].split(":", 1)[1]
            if token in contract.honeytokens and event.dest not in contract.approved_egress:
                findings.append(_make(
                    "honeytoken_tripwire", event,
                    f"honeytoken {token} observed leaving to unapproved dest {event.dest}",
                ))

        # --- critical: self-exfiltration ------------------------------------
        if event.kind == "egress" and (markers & _SENSITIVE):
            if event.dest not in contract.approved_egress:
                findings.append(_make(
                    "self_exfiltration", event,
                    f"sensitive markers {sorted(markers & _SENSITIVE)} sent to unapproved dest {event.dest}",
                ))

        # --- critical: new egress destination --------------------------------
        if event.kind == "egress" and event.dest:
            if event.dest not in contract.approved_egress:
                findings.append(_make(
                    "new_egress", event,
                    f"egress to {event.dest} not in contract allowlist {sorted(contract.approved_egress)}",
                ))

        # --- high: out-of-scope tool -----------------------------------------
        if event.kind == "tool_call" and event.scope:
            if event.scope not in contract.allowed_tool_scopes:
                findings.append(_make(
                    "out_of_scope_tool", event,
                    f"tool {event.tool} used scope {event.scope}; allowed {sorted(contract.allowed_tool_scopes)}",
                ))

        # --- high: egress volume spike ---------------------------------------
        if event.kind == "egress" and baseline is not None and baseline.egress_bytes_std > 0:
            z = (event.bytes_out - baseline.egress_bytes_mean) / baseline.egress_bytes_std
            if z > self.spike_sigma and event.bytes_out >= self.spike_floor_bytes:
                findings.append(_make(
                    "volume_spike", event,
                    f"egress {event.bytes_out} bytes is {z:.1f} sigma above baseline "
                    f"(mean {baseline.egress_bytes_mean:.0f})",
                ))

        # --- high: prompt injection -------------------------------------------
        injections = [m for m in markers if m.startswith("injection:")]
        if injections and event.kind in ("model_output", "tool_call"):
            findings.append(_make(
                "prompt_injection", event,
                f"injection marker {injections[0]} present in {event.kind} from {event.tool}",
            ))

        # --- high: data-ceiling breach -----------------------------------------
        if event.kind == "data_access" and event.records > contract.data_ceiling_records:
            findings.append(_make(
                "data_ceiling_breach", event,
                f"{event.records} records accessed vs ceiling {contract.data_ceiling_records}",
            ))

        # --- high: per-run budget breach ----------------------------------------
        if usage["actions"] > contract.max_actions_per_run:
            findings.append(_make(
                "run_budget_breach", event,
                f"run {event.run_id} exceeded action budget "
                f"({usage['actions']} > {contract.max_actions_per_run})",
            ))
        elif usage["bytes"] > contract.max_egress_bytes_per_run:
            findings.append(_make(
                "run_budget_breach", event,
                f"run {event.run_id} exceeded egress-byte budget "
                f"({usage['bytes']} > {contract.max_egress_bytes_per_run})",
            ))

        return findings
