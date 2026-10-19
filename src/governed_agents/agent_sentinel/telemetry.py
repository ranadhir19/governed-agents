"""Telemetry seam: adapters turn signals into events tagged with provenance.

Every event carries provenance: "live" (a real adapter) or "simulated"
(a seeded generator). The simulated feed ships with an injected rogue
sequence for demonstration; the rogue sequence is EXCLUDED from baseline
learning so it reads as an anomaly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np


class Provenance:
    LIVE = "live"
    SIMULATED = "simulated"


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float  # seconds since feed start
    agent_id: str
    run_id: str
    kind: str  # "tool_call" | "egress" | "data_access" | "model_output"
    tool: Optional[str] = None
    scope: Optional[str] = None
    dest: Optional[str] = None
    bytes_out: int = 0
    records: int = 0
    # e.g. {"honeytoken:honey-apikey-payment-ops"}, {"injection:ignore-prior"},
    # {"pii"}, {"pci"}
    payload_markers: frozenset = frozenset()
    provenance: str = Provenance.SIMULATED
    rogue: bool = False  # True only for the injected demonstration sequence


# Normal behaviour profiles per agent used by the simulated feed.
# (typical tools with scopes, typical dests, median egress bytes)
PROFILES: Dict[str, dict] = {
    "doc-summarizer": {
        "tools": [("docstore.get", "docs.read"), ("summarizer.run", "llm.summarize")],
        "dests": ["docstore.internal"],
        "median_bytes": 40_000,
        "median_records": 5,
    },
    "support-copilot": {
        "tools": [("crm.lookup", "crm.read"), ("crm.note", "crm.write"), ("chat.reply", "llm.chat")],
        "dests": ["crm.internal"],
        "median_bytes": 12_000,
        "median_records": 3,
    },
    "data-analyst": {
        "tools": [("warehouse.query", "dw.read"), ("chart.render", "bi.render")],
        "dests": ["warehouse.internal", "bi.internal"],
        "median_bytes": 250_000,
        "median_records": 200,
    },
    "code-reviewer": {
        "tools": [("repo.diff", "repo.read"), ("repo.comment", "repo.write"), ("pkg.resolve", "pkg.read")],
        "dests": ["git.internal", "pkg-mirror.internal"],
        "median_bytes": 90_000,
        "median_records": 0,
    },
    "payment-ops": {
        "tools": [("ledger.read", "ledger.read"), ("processor.charge", "payments.charge")],
        "dests": ["ledger.internal", "processor.example.com"],
        "median_bytes": 4_000,
        "median_records": 2,
    },
    "research-agent": {
        "tools": [("web.search", "web.search"), ("doc.fetch", "web.fetch"), ("notes.write", "notes.write")],
        "dests": ["search.example.com", "docs.internal"],
        "median_bytes": 120_000,
        "median_records": 0,
    },
}

ROGUE_DEST = "exfil.example.net"


class SimulatedFeed:
    """Seeded telemetry generator with an injected rogue sequence.

    baseline_window(n): normal behaviour only, provenance=simulated.
    live_stream(n): normal behaviour plus the deterministic rogue sequence
        (positions seeded). Rogue events are flagged rogue=True.
    """

    def __init__(self, seed: int = 7) -> None:
        self._rng = np.random.RandomState(seed)
        self._seq = 0
        self._ts = 0.0

    def _next(self, **kw) -> Event:
        self._seq += 1
        self._ts += float(self._rng.exponential(2.0))
        return Event(seq=self._seq, ts=self._ts, **kw)

    def _normal_event(self, agent_id: str, run_id: str) -> Event:
        prof = PROFILES[agent_id]
        rng = self._rng
        kind = rng.choice(["tool_call", "egress", "data_access"], p=[0.45, 0.35, 0.20])
        tool, scope = prof["tools"][rng.randint(len(prof["tools"]))]
        dest = prof["dests"][rng.randint(len(prof["dests"]))]
        bytes_out = int(prof["median_bytes"] * rng.lognormal(0, 0.5)) if kind == "egress" else 0
        records = int(prof["median_records"] * rng.lognormal(0, 0.4)) if kind == "data_access" else 0
        markers = frozenset()
        if agent_id == "payment-ops" and kind == "data_access":
            markers = frozenset({"pci"})
        if agent_id == "support-copilot" and kind == "data_access":
            markers = frozenset({"pii"})
        return self._next(
            agent_id=agent_id,
            run_id=run_id,
            kind=kind,
            tool=tool,
            scope=scope,
            dest=dest if kind == "egress" else None,
            bytes_out=bytes_out,
            records=records,
            payload_markers=markers,
        )

    def baseline_window(self, n_per_agent: int = 400) -> List[Event]:
        events: List[Event] = []
        for agent_id in sorted(PROFILES):
            for r in range(n_per_agent // 20):
                run_id = f"baseline-{agent_id}-{r}"
                for _ in range(20):
                    events.append(self._normal_event(agent_id, run_id))
        events.sort(key=lambda e: e.seq)
        return events

    def _rogue_sequence(self) -> List[Event]:
        """Deterministic rogue sequence. Flagged rogue=True, never baselined."""
        R: List[Event] = []
        # 1. payment-ops exfiltrates a honeytoken to an unknown host (critical x3)
        R.append(self._next(agent_id="payment-ops", run_id="rogue-1", kind="egress",
                            tool="processor.charge", scope="payments.charge",
                            dest=ROGUE_DEST, bytes_out=2_000_000,
                            payload_markers=frozenset({"honeytoken:honey-apikey-payment-ops", "pci"}),
                            rogue=True))
        # 2. code-reviewer invokes an out-of-scope tool (high)
        R.append(self._next(agent_id="code-reviewer", run_id="rogue-2", kind="tool_call",
                            tool="repo.admin", scope="repo.admin", rogue=True))
        # 3. research-agent egress volume spike to an approved dest (high)
        R.append(self._next(agent_id="research-agent", run_id="rogue-3", kind="egress",
                            tool="doc.fetch", scope="web.fetch", dest="docs.internal",
                            bytes_out=60_000_000, rogue=True))
        # 4. support-copilot consumes a prompt-injected tool output (high)
        R.append(self._next(agent_id="support-copilot", run_id="rogue-4", kind="model_output",
                            tool="crm.lookup", scope="crm.read",
                            payload_markers=frozenset({"injection:ignore-prior-instructions"}),
                            rogue=True))
        # 5. payment-ops breaches its data ceiling: 500 records vs ceiling 10 (high)
        R.append(self._next(agent_id="payment-ops", run_id="rogue-5", kind="data_access",
                            tool="ledger.read", scope="ledger.read", records=500,
                            payload_markers=frozenset({"pci"}), rogue=True))
        # 6. payment-ops trips a second honeytoken: circuit-breaker trigger (critical)
        R.append(self._next(agent_id="payment-ops", run_id="rogue-6", kind="egress",
                            tool="processor.charge", scope="payments.charge",
                            dest=ROGUE_DEST, bytes_out=900_000,
                            payload_markers=frozenset({"honeytoken:honey-customer-payment-ops", "pii"}),
                            rogue=True))
        return R

    def live_stream(self, n_per_agent: int = 120) -> Tuple[List[Event], List[Event]]:
        """Return (events, rogue_events). Rogue sequence interleaved at seeded spots."""
        from dataclasses import replace

        events: List[Event] = []
        for agent_id in sorted(PROFILES):
            for r in range(n_per_agent // 20):
                run_id = f"live-{agent_id}-{r}"
                for _ in range(20):
                    events.append(self._normal_event(agent_id, run_id))
        rogues = self._rogue_sequence()
        # Interleave rogues at seeded positions across the stream.
        positions = sorted(self._rng.choice(len(events), size=len(rogues), replace=False))
        for pos, rogue in zip(positions, rogues):
            events.insert(pos, rogue)
        # Re-stamp seq/ts monotonically in stream order (rogues were built last).
        restamped: List[Event] = []
        ts = 0.0
        for i, e in enumerate(events, start=1):
            ts += float(self._rng.exponential(2.0))
            restamped.append(replace(e, seq=i, ts=ts))
        rogue_seqs = {id(r) for r in rogues}
        restamped_rogues = [e for e, orig in zip(restamped, events) if id(orig) in rogue_seqs]
        return restamped, restamped_rogues
