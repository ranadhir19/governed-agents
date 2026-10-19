"""Deterministic synthetic workforce data.

All data is SYNTHETIC, generated from a seeded RNG. No real mailboxes,
tickets, repositories, or people are involved. The generator plants:

  * genuine discretion: in ``invoice-triage``, the pre-decision field
    ``amount`` separates outcomes (senior review vs auto-process) by a wide
    margin over enough minority cases;
  * trap 1 (``access-request``): ``approval_timestamp`` is perfectly
    predictive but observed AFTER the decision -- the leakage guard must
    reject it;
  * trap 2 (``refund-request``): ``risk_score`` separates outcomes with
    margin >= 0.45 but over only 5 minority cases -- the minority rule must
    reject it.

Every field observation carries an ``observed_time``. Pre-decision fields are
always observed at or before ``decision_time``; the trap-1 field is observed
after it. Times are integer day offsets from an arbitrary epoch.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .discretion import FieldSpec

TASK_TYPES = [
    "invoice-triage",
    "access-request",
    "refund-request",
    "expense-review",
    "vendor-onboarding",
    "incident-triage",
    "document-approval",
    "shift-swap",
    "data-extract",
    "contract-review",
]

# Candidate fields examined per task type (name -> numeric?).
FIELD_SPECS: Dict[str, List[FieldSpec]] = {
    "invoice-triage": [FieldSpec("amount"), FieldSpec("vendor_tenure"),
                       FieldSpec("line_items")],
    "access-request": [FieldSpec("requester_tenure"), FieldSpec("approval_timestamp"),
                       FieldSpec("scope_items")],
    "refund-request": [FieldSpec("risk_score"), FieldSpec("amount"),
                       FieldSpec("customer_tenure")],
}
for _t in TASK_TYPES:
    if _t not in FIELD_SPECS:
        FIELD_SPECS[_t] = [FieldSpec("amount"), FieldSpec("risk_score"),
                           FieldSpec("tenure")]


def _obs(value: Any, decision_time: float, pre: bool = True) -> Dict[str, Any]:
    """A field observation. Pre-decision fields are never observed after the decision."""
    delta = -float(np.random.uniform(0.1, 2.0)) if pre else float(np.random.uniform(0.1, 1.0))
    return {"value": value, "observed_time": decision_time + delta}


def _ops() -> Dict[str, float]:
    return {
        "cycle_time": float(np.random.lognormal(1.0, 0.7)),
        "rework": float(np.random.random() < 0.15),
        "handoffs": float(np.random.poisson(1.5)),
        "tool_switches": float(np.random.poisson(3.0)),
        "after_hours": float(np.random.random() < 0.20),
        "batch_size": float(np.random.poisson(4) + 1),
        "sla_breach": float(np.random.random() < 0.10),
        "reopen": float(np.random.random() < 0.08),
    }


def _case(case_id: str, task_type: str, contributor_ref: str, day: float,
          outcome: int, fields: Dict[str, Dict[str, Any]], band: str = "",
          decision_time: Optional[float] = None) -> Dict[str, Any]:
    if decision_time is None:
        decision_time = day + float(np.random.uniform(0.2, 0.9))
    return {
        "case_id": case_id, "task_type": task_type,
        "contributor_ref": contributor_ref, "band": band,
        "created_time": day, "decision_time": decision_time,
        "outcome": outcome, "fields": fields, "ops": _ops(),
    }


def generate(seed: int = 7) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Generate the full synthetic dataset. Returns (cases, worker_ids)."""
    np.random.seed(seed)
    workers = ["W%03d" % (i + 1) for i in range(40)]
    cases: List[Dict[str, Any]] = []
    seq = 0

    def nid(prefix: str) -> str:
        nonlocal seq
        seq += 1
        return "%s-%05d" % (prefix, seq)

    # ---- invoice-triage: planted discretion on `amount` ----
    # Bands engineered for the cohort-suppression demo:
    #   "0-1k": 27 cases, spread contributors (ok)
    #   "1k-5k": 10 cases, 8 by W007 (suppressed: single share 80% > 50%)
    #   "5k-50k": 20 cases across 12 contributors (ok)
    #   "50k+": 3 cases (suppressed: n < 5)
    band_plan = [
        ("0-1k", 54, (50.0, 1000.0), None),
        ("1k-5k", 20, (1000.0, 5000.0), "W007"),
        ("5k-50k", 40, (5000.0, 50000.0), None),
        ("50k+", 3, (50000.0, 90000.0), None),
    ]
    wide_workers = ["W%03d" % i for i in range(1, 13)]
    wi = 0
    for band, n, (lo, hi), dom in band_plan:
        for j in range(n):
            amount = float(np.random.uniform(lo, hi))
            truth = 1 if amount >= 5000.0 else 0
            outcome = truth if np.random.random() < 0.90 else 1 - truth
            if dom is not None and j < 16:
                w = dom
            elif band == "5k-50k":
                w = wide_workers[wi % len(wide_workers)]; wi += 1
            else:
                w = workers[np.random.randint(0, len(workers))]
            day = float(np.random.uniform(0, 60))
            dt = day + float(np.random.uniform(0.2, 0.9))
            fields = {
                "amount": _obs(amount, dt, pre=True),
                "vendor_tenure": _obs(float(np.random.uniform(0, 10)), dt, pre=True),
                "line_items": _obs(float(np.random.poisson(6) + 1), dt, pre=True),
            }
            cases.append(_case(nid("INV"), "invoice-triage", w, day, outcome, fields, band, decision_time=dt))

    # ---- access-request: TRAP 1 (leakage) ----
    for _ in range(40):
        outcome = int(np.random.random() < 0.5)
        w = workers[np.random.randint(0, len(workers))]
        day = float(np.random.uniform(0, 60))
        dt = day + float(np.random.uniform(0.2, 0.9))
        fields = {
            "requester_tenure": _obs(float(np.random.uniform(0, 8)), dt, pre=True),
            "scope_items": _obs(float(np.random.poisson(2) + 1), dt, pre=True),
            # Perfectly predictive -- and perfectly useless: it exists only
            # because the decision was taken.
            "approval_timestamp": _obs(dt + 0.05, dt, pre=False) if outcome == 1
            else {"value": None, "observed_time": dt - 0.1},
        }
        cases.append(_case(nid("ACC"), "access-request", w, day, outcome, fields, decision_time=dt))

    # ---- refund-request: TRAP 2 (small-n) ----
    # 12 cases: 7 auto (y=0, low risk), 5 escalate (y=1, high risk).
    # margin ~= 1.0 >= 0.45, but minority_n = 5 < 8 -> must be rejected.
    for i in range(12):
        outcome = 1 if i >= 7 else 0
        risk = float(np.random.uniform(0.9, 1.0)) if outcome else float(np.random.uniform(0.0, 0.1))
        w = workers[np.random.randint(0, len(workers))]
        day = float(np.random.uniform(0, 60))
        dt = day + float(np.random.uniform(0.2, 0.9))
        fields = {
            "risk_score": _obs(risk, dt, pre=True),
            "amount": _obs(float(np.random.uniform(10, 400)), dt, pre=True),
            "customer_tenure": _obs(float(np.random.uniform(0, 6)), dt, pre=True),
        }
        cases.append(_case(nid("REF"), "refund-request", w, day, outcome, fields, decision_time=dt))

    # ---- remaining task types: noise (expect abstention) ----
    for tt in TASK_TYPES[3:]:
        prefix = "".join(p[0] for p in tt.split("-")).upper()
        for _ in range(30):
            outcome = int(np.random.random() < 0.5)
            w = workers[np.random.randint(0, len(workers))]
            day = float(np.random.uniform(0, 60))
            dt = day + float(np.random.uniform(0.2, 0.9))
            fields = {
                "amount": _obs(float(np.random.lognormal(6, 1.2)), dt, pre=True),
                "risk_score": _obs(float(np.random.random()), dt, pre=True),
                "tenure": _obs(float(np.random.uniform(0, 10)), dt, pre=True),
            }
            cases.append(_case(nid(prefix), tt, w, day, outcome, fields, decision_time=dt))

    return cases, workers


def generate_shadow_cases(seed: int = 11, n: int = 64) -> List[Dict[str, Any]]:
    """Shadow-mode cases for the invoice-triage routing skill.

    The twin predicts senior-review iff amount >= 5000. The human decides
    independently (the seal keeps the labels uncontaminated); human noise is
    an 8% flip, so expected agreement is ~0.92.
    """
    np.random.seed(seed)
    out = []
    for i in range(n):
        amount = float(np.random.lognormal(8.2, 1.1))
        pred = 1 if amount >= 5000.0 else 0
        far = abs(amount - 5000.0) / 5000.0 > 0.5
        if far:
            confidence, flip = 0.98, 0.02
        else:
            confidence, flip = 0.92, 0.08
        human = pred if np.random.random() >= flip else 1 - pred
        out.append({"case_id": "SH-%04d" % (i + 1), "task_type": "invoice-triage",
                    "amount": amount, "prediction": pred, "confidence": confidence,
                    "human_decision": human,
                    "created_time": float(i)})
    return out
