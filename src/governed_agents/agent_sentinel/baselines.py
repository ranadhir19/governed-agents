"""Phase 1a: per-agent behavioural baselines from a normal telemetry window.

Baselines are learned ONLY from the normal window. The rogue demonstration
sequence is never part of baseline learning, so it reads as an anomaly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from governed_agents.agent_sentinel.telemetry import Event


@dataclass
class Baseline:
    agent_id: str
    tools_seen: frozenset
    dests_seen: frozenset
    egress_bytes_mean: float
    egress_bytes_std: float
    n_events: int


def learn_baselines(events: List[Event]) -> Dict[str, Baseline]:
    """Learn one baseline per agent from normal-window events."""
    by_agent: Dict[str, List[Event]] = {}
    for e in events:
        if e.rogue:
            raise ValueError("rogue events must never enter baseline learning")
        by_agent.setdefault(e.agent_id, []).append(e)
    out: Dict[str, Baseline] = {}
    for agent_id, evs in by_agent.items():
        tools = frozenset(e.tool for e in evs if e.tool)
        dests = frozenset(e.dest for e in evs if e.kind == "egress" and e.dest)
        sizes = np.array([e.bytes_out for e in evs if e.kind == "egress"], dtype=float)
        out[agent_id] = Baseline(
            agent_id=agent_id,
            tools_seen=tools,
            dests_seen=dests,
            egress_bytes_mean=float(sizes.mean()) if len(sizes) else 0.0,
            egress_bytes_std=float(sizes.std()) if len(sizes) else 0.0,
            n_events=len(evs),
        )
    return out
