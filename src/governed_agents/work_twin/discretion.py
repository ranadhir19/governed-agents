"""Discretion, measured -- never asserted.

Nine of the ten task dimensions are arithmetic over the data. The tenth,
discretion, is measured: a task type counts as rule-like only if some
NON-LEAKING recorded field separates its outcomes by a wide margin
(>= 0.45) over enough minority cases (>= 8).

The leakage guard rejects fields that exist only because a decision was
taken. Each field observation carries an ``observed_time``; a field is
rejected for a task type when it is present in any case with
``observed_time > decision_time``, or when its spec is flagged
``post_decision`` at generation. Timestamps of the approval itself are the
canonical example: they are perfectly predictive and perfectly useless.

When no non-leaking field qualifies, abstention is the result:
"nothing recorded explains this decision" -- the honest fork between genuine
expertise and an undocumented process, which needs a human who knows the work.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

MIN_MARGIN = 0.45
MIN_MINORITY = 8
ABSTAIN_REASON = "nothing recorded explains this decision"


@dataclass
class FieldSpec:
    name: str
    numeric: bool = True
    post_decision: bool = False  # provenance flag from the generator


@dataclass
class FieldAssessment:
    name: str
    margin: Optional[float]
    minority_n: int
    rejected: bool
    reject_reason: Optional[str] = None


@dataclass
class DiscretionResult:
    task_type: str
    verdict: str  # "rule_like" or "abstain"
    basis_field: Optional[str]
    margin: Optional[float]
    minority_n: int
    assessments: List[FieldAssessment] = field(default_factory=list)
    reason: Optional[str] = None


def _field_values(cases: List[Dict[str, Any]], name: str) -> List[Tuple[Any, float, float]]:
    """(value, observed_time, decision_time) triples for non-null observations."""
    out = []
    for c in cases:
        obs = c["fields"].get(name)
        if obs is None or obs.get("value") is None:
            continue
        out.append((obs["value"], float(obs["observed_time"]), float(c["decision_time"])))
    return out


def leakage_check(cases: List[Dict[str, Any]], spec: FieldSpec) -> Optional[str]:
    """Return a rejection reason if the field leaks the decision, else None."""
    if spec.post_decision:
        return "leakage: field flagged post-decision at source"
    for _value, observed_time, decision_time in _field_values(cases, spec.name):
        if observed_time > decision_time:
            return ("leakage: field observed after the decision was taken "
                    "(exists only because a decision was taken)")
    return None


def _margin_for(cases: List[Dict[str, Any]], name: str) -> Optional[float]:
    vals = [(c["fields"][name]["value"], int(c["outcome"]))
            for c in cases
            if c["fields"].get(name) and c["fields"][name].get("value") is not None]
    if len(vals) < 2:
        return None
    xs = np.array([v for v, _ in vals], dtype=float)
    ys = np.array([y for _, y in vals], dtype=float)
    if np.all(xs == xs[0]):
        return None
    cut = float(np.median(xs))
    hi = ys[xs > cut]
    lo = ys[xs <= cut]
    if len(hi) == 0 or len(lo) == 0:
        return None
    return abs(float(hi.mean()) - float(lo.mean()))


def measure_discretion(
    cases: List[Dict[str, Any]],
    task_type: str,
    field_specs: List[FieldSpec],
    min_margin: float = MIN_MARGIN,
    min_minority: int = MIN_MINORITY,
) -> DiscretionResult:
    members = [c for c in cases if c.get("task_type") == task_type]
    outcomes = np.array([int(c["outcome"]) for c in members])
    minority_n = int(min((outcomes == 1).sum(), (outcomes == 0).sum())) if len(members) else 0

    assessments: List[FieldAssessment] = []
    best: Optional[Tuple[str, float]] = None
    for spec in field_specs:
        leak_reason = leakage_check(members, spec)
        if leak_reason is not None:
            assessments.append(FieldAssessment(spec.name, None, minority_n, True, leak_reason))
            continue
        margin = _margin_for(members, spec.name)
        if margin is None:
            assessments.append(FieldAssessment(spec.name, None, minority_n, True,
                                               "field has no variation to separate on"))
            continue
        if margin < min_margin:
            assessments.append(FieldAssessment(
                spec.name, margin, minority_n, True,
                "margin %.3f below %.2f threshold" % (margin, min_margin)))
            continue
        if minority_n < min_minority:
            assessments.append(FieldAssessment(
                spec.name, margin, minority_n, True,
                "margin %.3f qualifies but minority cases %d below minimum %d"
                % (margin, minority_n, min_minority)))
            continue
        assessments.append(FieldAssessment(spec.name, margin, minority_n, False))
        if best is None or margin > best[1]:
            best = (spec.name, margin)

    if best is not None:
        return DiscretionResult(task_type, "rule_like", best[0], best[1],
                                minority_n, assessments)
    # Was there a field that would have qualified but for the guard?
    near = [a for a in assessments
            if a.margin is not None and a.margin >= min_margin and a.rejected]
    reason = ABSTAIN_REASON
    if near:
        reason = "%s; guarded fields that would have qualified: %s" % (
            ABSTAIN_REASON,
            ", ".join("%s (%s)" % (a.name, a.reject_reason) for a in near))
    return DiscretionResult(task_type, "abstain", None, None, minority_n,
                            assessments, reason)


def arithmetic_dimensions(cases: List[Dict[str, Any]], task_type: str) -> Dict[str, float]:
    """The nine arithmetic dimensions. Pure functions of the case data."""
    members = [c for c in cases if c.get("task_type") == task_type]
    n = len(members)
    if n == 0:
        return {}
    ops = [c.get("ops", {}) for c in members]
    get = lambda k, d=0.0: np.array([float(o.get(k, d)) for o in ops])
    return {
        "volume": float(n),
        "cycle_time_mean": float(get("cycle_time").mean()),
        "rework_rate": float(get("rework").mean()),
        "handoff_mean": float(get("handoffs").mean()),
        "tool_switch_mean": float(get("tool_switches").mean()),
        "after_hours_share": float(get("after_hours").mean()),
        "batch_size_mean": float(get("batch_size").mean()),
        "sla_breach_rate": float(get("sla_breach").mean()),
        "reopen_rate": float(get("reopen").mean()),
    }


def task_profile(cases: List[Dict[str, Any]], task_type: str,
                 field_specs: List[FieldSpec]) -> Dict[str, Any]:
    """Ten dimensions: nine arithmetic, one measured (discretion)."""
    dims = arithmetic_dimensions(cases, task_type)
    disc = measure_discretion(cases, task_type, field_specs)
    dims["discretion"] = {
        "verdict": disc.verdict,
        "basis_field": disc.basis_field,
        "margin": disc.margin,
        "minority_n": disc.minority_n,
    }
    return {"task_type": task_type, "dimensions": dims, "detail": disc}
