"""Smoke tests for the work twin.

Run from the repo root:  PYTHONPATH=src python3 04-work-twin/tests/test_smoke.py
"""

import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from governed_agents.work_twin import (  # noqa: E402
    Plane, UpOnlyStore, Record, PersonalTwin, ProfessionalTwin, WorkingTwin,
    cohort_table, measure_discretion, FieldSpec, ShadowLog,
    Level, SkillState, evaluate_step, advance,
    generate, generate_shadow_cases, TASK_TYPES, FIELD_SPECS, deployment_gate,
)
from governed_agents.work_twin import cohort as cohort_mod  # noqa: E402

CASES, _WORKERS = generate(7)
N_TESTS = 0


def check(name, cond, detail=""):
    global N_TESTS
    N_TESTS += 1
    status = "ok" if cond else "FAIL"
    print("[%s] %s %s" % (status, name, detail))
    if not cond:
        raise AssertionError(name)


# 1. up-only: working-plane query cannot see personal records
store = UpOnlyStore()
store.write(Record("r1", Plane.PERSONAL, "commitment", {"text": "x"}, "worker"), Plane.PERSONAL)
seen = store.query(Plane.WORKING, kind="commitment")
check("up_only_flow", len(seen) == 0, "working plane sees %d personal records" % len(seen))

# 2. downward promote refused in code
try:
    store.promote("r1", Plane.PERSONAL, authorized_by="worker")
    check("promote_down_refused", False, "downward promote accepted")
except ValueError:
    check("promote_down_refused", True)

# 3. personal records promote only on worker authorization
try:
    store.promote("r1", Plane.PROFESSIONAL, authorized_by="employer")
    check("promote_personal_worker_only", False, "employer promote accepted")
except PermissionError:
    check("promote_personal_worker_only", True)

# 4. no person-level function exists in the cohort module (AST over signatures)
FORBIDDEN = {"person", "person_id", "manager", "manager_id", "team", "team_id",
             "worker", "worker_id", "user", "user_id", "employee", "employee_id",
             "individual", "subject"}
tree = ast.parse(open(cohort_mod.__file__).read())
bad = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = [a.arg for a in node.args.args + node.args.kwonlyargs]
        hit = [p for p in params if p.lower() in FORBIDDEN]
        if hit:
            bad.append("%s(%s)" % (node.name, ",".join(hit)))
check("no_person_level_function", not bad, "offenders: %s" % bad)

# 5. suppression: minimum cohort of 5
cells = cohort_table(CASES, "invoice-triage", band_of=lambda c: c["band"])
small = [c for c in cells if c.band == "50k+"][0]
check("suppression_min_cohort",
      small.status == "suppressed" and "5" in (small.reason or ""),
      small.display())

# 6. suppression: maximum single-contributor share 50%
dom = [c for c in cells if c.band == "1k-5k"][0]
check("suppression_max_share",
      dom.status == "suppressed" and "50%" in (dom.reason or ""),
      dom.display())

# 7. suppressed cells are never blank/zero
for c in cells:
    if c.status == "suppressed":
        d = c.display()
        check("suppressed_never_blank_%s" % c.band.replace("+", "plus"),
              d.startswith("suppressed (") and bool(c.reason), d)
        break

# 8. planted discretion recovered
r = measure_discretion(CASES, "invoice-triage", FIELD_SPECS["invoice-triage"])
check("planted_discretion_recovered",
      r.verdict == "rule_like" and r.basis_field == "amount" and r.margin >= 0.45,
      "margin=%.3f minority=%d" % (r.margin or 0, r.minority_n))

# 9. trap 1: leaking field caught, task not reported rule-like
r = measure_discretion(CASES, "access-request", FIELD_SPECS["access-request"])
leak = [a for a in r.assessments if a.name == "approval_timestamp"][0]
check("trap1_leakage_caught",
      leak.rejected and "leakage" in (leak.reject_reason or "") and r.verdict != "rule_like",
      leak.reject_reason or "")

# 10. trap 2: small-n field caught, task not reported rule-like
r = measure_discretion(CASES, "refund-request", FIELD_SPECS["refund-request"])
smalln = [a for a in r.assessments if a.name == "risk_score"][0]
check("trap2_smalln_caught",
      smalln.rejected and "minority" in (smalln.reject_reason or "") and r.verdict != "rule_like",
      smalln.reject_reason or "")

# 11. abstention is a result with the honest reason
r = measure_discretion(CASES, "expense-review", FIELD_SPECS["expense-review"])
check("abstention",
      r.verdict == "abstain" and r.reason and "nothing recorded explains" in r.reason,
      r.reason or "")

# 12. shadow seal: no commit -> no decision; no decision -> no reveal
log = ShadowLog()
try:
    log.record_human_decision("nope", 1)
    check("shadow_seal_commit_first", False)
except KeyError:
    check("shadow_seal_commit_first", True)
log.commit("c1", 1, 0.9)
try:
    log.reveal("c1")
    check("shadow_seal_reveal_after_decision", False)
except PermissionError:
    check("shadow_seal_reveal_after_decision", True)
# revealed-then-decided labels are refused as contaminated
log.record_human_decision("c1", 1)
log.reveal("c1")
try:
    log.record_human_decision("c1", 0)
    check("shadow_seal_no_redecide", False)
except (PermissionError, ValueError):
    check("shadow_seal_no_redecide", True)

# 13. shadow agreement/ECE on seeded data meet the ladder bars
sc = generate_shadow_cases(11, 80)
log = ShadowLog()
for s in sc:
    log.commit(s["case_id"], s["prediction"], s["confidence"])
    log.record_human_decision(s["case_id"], s["human_decision"])
check("shadow_metrics", log.agreement() >= 0.90 and log.expected_calibration_error() <= 0.10,
      "agreement=%.3f ece=%.3f" % (log.agreement(), log.expected_calibration_error()))

# 14. ladder: five gates evaluated; L3->L4 needs agreement >= 0.90
state = SkillState("s", "invoice-triage", level=Level.L3, n_shadow=80,
                   agreement=0.89, ece=0.05, clean_basis=True, veto_active=False)
rep = evaluate_step(state)
check("ladder_five_gates", len(rep.gates) == 5, "%d gates" % len(rep.gates))
check("ladder_l3_l4_bar", not rep.can_advance, "0.89 < 0.90 must block")
state.agreement = 0.96
rep = evaluate_step(state)
check("ladder_l3_l4_pass", rep.can_advance, "0.96 >= 0.90 must pass")

# 15. ladder: ECE gate bites
state = SkillState("s", "invoice-triage", level=Level.L1, n_shadow=80,
                   agreement=0.99, ece=0.15, clean_basis=True, veto_active=False)
rep = evaluate_step(state)
check("ladder_ece_gate", not rep.can_advance, "ece 0.15 > 0.10 must block")

# 16. ladder: veto gate bites; and no savings language anywhere in reports
state = SkillState("s", "invoice-triage", level=Level.L1, n_shadow=80,
                   agreement=0.99, ece=0.01, clean_basis=True, veto_active=True)
rep = evaluate_step(state)
text = rep.summary().lower()
check("ladder_veto_gate", not rep.can_advance, "active veto must block")
check("ladder_no_savings", "$" not in text and "saving" not in text.replace("not a saving", ""),
      "report must not monetize candidacy")

# 17. working twin: vetoed actions cannot execute; unvetoed can
store2 = UpOnlyStore()
wt = WorkingTwin(store2)
wt.grant("invoice-routing", 4)
p = wt.propose("invoice-routing", {"route": "x"}, "contract-1")
wt.worker_veto(p.proposal_id, "reason")
try:
    wt.execute(p.proposal_id)
    check("veto_blocks_execute", False)
except PermissionError:
    check("veto_blocks_execute", True)
p2 = wt.propose("invoice-routing", {"route": "y"}, "contract-1")
wt.execute(p2.proposal_id)
check("unvetoed_executes", p2.executed)
# ungranted skill cannot even propose
try:
    wt.propose("other-skill", {}, "contract-1")
    check("ungranted_refused", False)
except PermissionError:
    check("ungranted_refused", True)

# 18. deployment gate goes on the seeded build
go, proof = deployment_gate(7)
check("deployment_gate", go and all(c["passed"] for c in proof["checks"]),
      "go=%s" % go)

# 19. professional twin: worker correction keeps history
store3 = UpOnlyStore()
prof = ProfessionalTwin(store3)
rid = prof.publish("evidence", {"text": "v1"}, "employer")
prof.correct(rid, {"text": "v2"})
rec = store3._records[rid]
check("worker_correction", rec.payload["text"] == "v2" and len(rec.history) == 1)

print("\n%d/%d tests passed" % (N_TESTS, N_TESTS))
