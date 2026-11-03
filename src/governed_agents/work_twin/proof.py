"""Build proof: deployment is gated on measurement, not on claims.

``deployment_gate`` regenerates the synthetic dataset from a known seed and
requires the deployed code to:

  1. recover the planted discretion (invoice-triage is rule-like on `amount`);
  2. catch trap 1 (the leaking `approval_timestamp` is rejected by the guard,
     and access-request is NOT reported rule-like);
  3. catch trap 2 (`risk_score` is rejected on the minority-cases rule, and
     refund-request is NOT reported rule-like).

If any check fails, the gate returns go=False with the failing check named.
"""

from typing import Any, Dict, List, Tuple

from .cohort import cohort_table
from .discretion import measure_discretion
from .generate import FIELD_SPECS, generate


def deployment_gate(seed: int = 7) -> Tuple[bool, Dict[str, Any]]:
    cases, _workers = generate(seed)
    checks: List[Dict[str, Any]] = []

    r_inv = measure_discretion(cases, "invoice-triage", FIELD_SPECS["invoice-triage"])
    ok1 = r_inv.verdict == "rule_like" and r_inv.basis_field == "amount"
    checks.append({"check": "planted discretion recovered",
                   "passed": ok1,
                   "detail": "verdict=%s basis=%s margin=%.3f" % (
                       r_inv.verdict, r_inv.basis_field, r_inv.margin or 0.0)})

    r_acc = measure_discretion(cases, "access-request", FIELD_SPECS["access-request"])
    leak_rejected = any(a.name == "approval_timestamp" and a.rejected
                        and "leakage" in (a.reject_reason or "")
                        for a in r_acc.assessments)
    ok2 = leak_rejected and r_acc.verdict != "rule_like"
    checks.append({"check": "trap 1 (leaking field) caught",
                   "passed": ok2,
                   "detail": "approval_timestamp rejected by guard: %s; verdict=%s"
                             % (leak_rejected, r_acc.verdict)})

    r_ref = measure_discretion(cases, "refund-request", FIELD_SPECS["refund-request"])
    smalln_rejected = any(a.name == "risk_score" and a.rejected
                          and "minority" in (a.reject_reason or "")
                          for a in r_ref.assessments)
    ok3 = smalln_rejected and r_ref.verdict != "rule_like"
    checks.append({"check": "trap 2 (small-n field) caught",
                   "passed": ok3,
                   "detail": "risk_score rejected on minority rule: %s; verdict=%s"
                             % (smalln_rejected, r_ref.verdict)})

    # The cohort boundary must hold on the same build.
    cells = cohort_table(cases, "invoice-triage", band_of=lambda c: c["band"])
    suppressed = [c for c in cells if c.status == "suppressed"]
    ok4 = len(suppressed) >= 2 and all(c.reason for c in suppressed)
    checks.append({"check": "suppression rules hold",
                   "passed": ok4,
                   "detail": "%d cells suppressed with reasons" % len(suppressed)})

    go = all(c["passed"] for c in checks)
    return go, {"seed": seed, "go": go, "checks": checks}
