"""Quickstart for the work twin (application 4 of 6).

Runs a compact seeded pipeline: synthetic data -> discretion measurement
(including both traps) -> shadow metrics -> ladder verdict -> deployment gate.

Run from the repo root:  PYTHONPATH=src python3 examples/04_work_twin_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.work_twin import (  # noqa: E402
    Plane, UpOnlyStore, Record, cohort_table, measure_discretion,
    ShadowLog, SkillState, Level, evaluate_step,
    generate, generate_shadow_cases, FIELD_SPECS, deployment_gate,
)


def main():
    cases, workers = generate(7)
    print("synthetic data: %d cases, %d workers" % (len(cases), len(workers)))

    # Up-only flow in one line: the employer cannot read the personal plane.
    store = UpOnlyStore()
    store.write(Record("c1", Plane.PERSONAL, "commitment", {"text": "draft Q3 notes"},
                       "worker"), Plane.PERSONAL)
    print("working-plane read of personal commitments: %d (must be 0)"
          % len(store.query(Plane.WORKING, kind="commitment")))

    # Discretion: planted rule recovered, both traps caught.
    r = measure_discretion(cases, "invoice-triage", FIELD_SPECS["invoice-triage"])
    print("invoice-triage: %s on '%s' (margin %.3f)" % (r.verdict, r.basis_field, r.margin))
    r = measure_discretion(cases, "access-request", FIELD_SPECS["access-request"])
    leak = [a for a in r.assessments if a.name == "approval_timestamp"][0]
    print("trap 1: %s" % leak.reject_reason)
    r = measure_discretion(cases, "refund-request", FIELD_SPECS["refund-request"])
    smalln = [a for a in r.assessments if a.name == "risk_score"][0]
    print("trap 2: %s" % smalln.reject_reason)

    # Cohort suppression.
    cells = cohort_table(cases, "invoice-triage", band_of=lambda c: c["band"])
    for c in cells:
        print("cohort %-6s -> %s" % (c.band, c.display()))

    # Shadow metrics feed the ladder.
    sc = generate_shadow_cases(11, 80)
    log = ShadowLog()
    for s in sc:
        log.commit(s["case_id"], s["prediction"], s["confidence"])
        log.record_human_decision(s["case_id"], s["human_decision"])
    print("shadow: n=%d agreement=%.3f ece=%.3f"
          % (len(sc), log.agreement(), log.expected_calibration_error()))

    state = SkillState("invoice-routing", "invoice-triage", level=Level.L3,
                       n_shadow=len(sc), agreement=log.agreement(),
                       ece=log.expected_calibration_error(),
                       clean_basis=True, veto_active=False)
    rep = evaluate_step(state)
    print("ladder L3->L4: %s" % ("advance" if rep.can_advance else "blocked"))

    go, _ = deployment_gate(7)
    print("deployment gate: %s" % ("GO" if go else "NO-GO"))


if __name__ == "__main__":
    main()
