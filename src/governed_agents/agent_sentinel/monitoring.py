"""Platform monitoring bus (stub).

Containment and evaluation outcomes are reported here as structured
events. A containment action is reported as a self-healing action with
its incident reference, so platform monitoring sees it as managed
remediation rather than an unexplained outage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class MonitoringEvent:
    ts: float
    category: str  # "finding" | "gate" | "self_healing" | "eval" | "info"
    summary: str
    detail: Dict[str, Any] = field(default_factory=dict)


class MonitoringBus:
    def __init__(self) -> None:
        self._events: List[MonitoringEvent] = []

    def emit(self, category: str, summary: str, ts: float, **detail: Any) -> MonitoringEvent:
        ev = MonitoringEvent(ts=ts, category=category, summary=summary, detail=dict(detail))
        self._events.append(ev)
        return ev

    def events(self, category: str = None) -> List[MonitoringEvent]:
        if category is None:
            return list(self._events)
        return [e for e in self._events if e.category == category]

    def __len__(self) -> int:
        return len(self._events)
