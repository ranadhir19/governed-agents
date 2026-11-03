"""Smoke tests for the improvement loop (seeded, deterministic)."""

import copy
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from governed_agents.improvement_loop import (
    AuditLedger,
    ChecklistItem,
    Critic,
    CriticPanel,
    PanelResult,
    build_default_panel,
    Directive,
    Diagnostician,
    Reviser,
    propose_plan,
    Checkpoint,
    CheckpointManager,
    CheckpointError,
    StateClass,
    FaultCategory,
    Fault,
    Investigator,
    Healer,
    RecoveryReport,
    GoalDriftMonitor,
    LoopConfig,
    Termination,
    ImprovementEngine,
)

import numpy as np

SEED = 7


def _engine(**kw):
    cfg = LoopConfig(task="t", seed=SEED, **kw)
    return ImprovementEngine(cfg)


def test_critic_scores_fraction_of_checklist():
    panel = build_default_panel()
    plan = propose_plan("t", np.random.default_rng(SEED))
    res = panel.evaluate(plan)
    # completeness critic: 9 items; the sparse draft passes few
    comp = res.per_critic["completeness"]
    assert comp.total == 9
    assert abs(comp.score - len(comp.passed_items) / 9) < 1e-12
    assert 0.0 <= res.composite <= 1.0


def test_composite_is_weighted_average():
    panel = build_default_panel()
    plan = propose_plan("t", np.random.default_rng(SEED))
    res = panel.evaluate(plan)
    wsum = sum(c.weight for c in panel.critics)
    expected = sum(c.weight * res.per_critic[c.name].score
                   for c in panel.critics) / wsum
    assert abs(res.composite - expected) < 1e-12


def test_pluggable_domain_critic_counts():
    panel = build_default_panel()
    before = panel.evaluate(propose_plan("t", np.random.default_rng(SEED)))
    panel.register(Critic("domain", weight=0.5, threshold=1.0,
                          items=[ChecklistItem("x", "x", lambda a: True)]))
    after = panel.evaluate(propose_plan("t", np.random.default_rng(SEED)))
    assert after.total_items == before.total_items + 1
    assert "domain" in after.per_critic


def test_diagnostician_targets_weakest_dimension():
    panel = build_default_panel()
    plan = propose_plan("t", np.random.default_rng(SEED))
    res = panel.evaluate(plan)
    directives = Diagnostician().diagnose(res)
    assert len(directives) > 0
    # weakest critic (lowest score) should own the top-priority directive
    weakest = min(res.per_critic.values(), key=lambda r: r.score).critic
    assert directives[0].dimension == weakest


def test_reviser_improves_score_deterministically():
    panel = build_default_panel()
    rng = np.random.default_rng(SEED)
    plan = propose_plan("t", rng)
    before = panel.evaluate(plan).composite
    directives = Diagnostician().diagnose(panel.evaluate(plan))
    new_plan, applied = Reviser(capability=4).revise(plan, directives, rng)
    after = panel.evaluate(new_plan).composite
    assert applied > 0
    assert after > before
    # deterministic: same seed -> same result
    rng2 = np.random.default_rng(SEED)
    plan2 = propose_plan("t", rng2)
    d2 = Diagnostician().diagnose(panel.evaluate(plan2))
    new2, _ = Reviser(capability=4).revise(plan2, d2, rng2)
    assert panel.evaluate(new2).composite == after


def test_engine_terminates_met_standard():
    rep = _engine(quality_threshold=0.85, max_iterations=12).run()
    assert rep.termination == Termination.MET_STANDARD
    assert rep.best_score >= 0.85
    assert rep.ledger_ok


def test_plateau_detection_terminates():
    panel = build_default_panel()
    panel.register(Critic("impossible", weight=0.2, threshold=1.0,
                          items=[ChecklistItem("never", "never", lambda a: False)]))
    eng = ImprovementEngine(LoopConfig(task="t", quality_threshold=1.0,
                                       plateau_k=3, seed=SEED), panel=panel)
    rep = eng.run()
    assert rep.termination == Termination.PLATEAU
    assert rep.best_score < 1.0


def test_budget_exhaustion_terminates():
    rep = _engine(quality_threshold=0.99, budget=12.0,
                  cost_per_iteration=5.0).run()
    assert rep.termination == Termination.BUDGET_EXHAUSTED
    assert rep.budget_spent <= 12.0 + 1e-9


def test_human_gate_denial_halts():
    eng = ImprovementEngine(
        LoopConfig(task="t", human_gates=(2,), seed=SEED),
        approver=lambda iteration, ctx: False)
    rep = eng.run()
    assert rep.termination == Termination.HALTED_BY_HUMAN
    assert rep.gate_decisions == [{"iteration": 2, "approved": False}]


def test_checkpoint_restore_returns_best_plan_and_anchor_holds():
    ledger = AuditLedger()
    ledger.append("a", {})
    mgr = CheckpointManager()
    plan = {"title": "best", "sections": {}}
    ckpt = mgr.capture(3, plan, 0.9, ledger, healthy=True)
    assert not ckpt.provisional
    ledger.append("b", {})  # ledger keeps growing after capture
    payload = mgr.restore(ckpt, FaultCategory.LOGIC, ledger)
    assert payload["best_plan"] == plan
    assert payload["best_score"] == 0.9
    # anchor: ledger was never rewound
    assert ledger.verify()
    assert ledger.count() >= ckpt.anchor["ledger_count"]


def test_provisional_checkpoint_never_a_restore_target():
    ledger = AuditLedger()
    mgr = CheckpointManager()
    ckpt = mgr.capture(1, {"title": "x"}, 0.5, ledger, healthy=False)
    assert ckpt.provisional
    assert mgr.latest_restorable() is None
    try:
        mgr.restore(ckpt, FaultCategory.RESOURCE, ledger)
        raise AssertionError("should have refused")
    except CheckpointError:
        pass


def test_rollback_denied_for_configuration():
    ledger = AuditLedger()
    mgr = CheckpointManager()
    ckpt = mgr.capture(2, {"title": "x"}, 0.5, ledger, healthy=True)
    try:
        mgr.restore(ckpt, FaultCategory.CONFIGURATION, ledger)
        raise AssertionError("should have refused")
    except CheckpointError as e:
        assert "secret" in str(e).lower()
    # transient and dependency also denied
    for cat in (FaultCategory.TRANSIENT, FaultCategory.DEPENDENCY):
        try:
            mgr.restore(ckpt, cat, ledger)
            raise AssertionError("should have refused")
        except CheckpointError:
            pass
    # resource and logic allowed
    mgr.restore(ckpt, FaultCategory.RESOURCE, ledger)
    mgr.restore(ckpt, FaultCategory.LOGIC, ledger)


def test_healer_recovers_resource_fault_and_keeps_lesson():
    monitor = []
    healer = Healer(monitor=monitor)
    calls = {"n": 0}

    def resume():
        calls["n"] += 1

    report = healer.handle(
        Fault(step="revise",
              error=RuntimeError("worker memory spike: heap exhausted"),
              iteration=3, metadata={}),
        {"resume_plan": resume, "probe": lambda: True})
    assert report.category == FaultCategory.RESOURCE
    assert report.recovered and report.verified
    assert calls["n"] == 1
    assert len(healer.lessons) == 1
    assert healer.lessons[0]["category"] == FaultCategory.RESOURCE
    assert any(e["event"] == "fault_classified" for e in monitor)


def test_investigator_classifies_all_categories():
    inv = Investigator()
    cases = [
        ("heap memory exhausted", {}, FaultCategory.RESOURCE),
        ("connection refused by service", {}, FaultCategory.DEPENDENCY),
        ("missing credential: revoked secret", {}, FaultCategory.CONFIGURATION),
        ("flaky write", {}, FaultCategory.TRANSIENT),
        ("off-by-one in merge", {}, FaultCategory.LOGIC),
    ]
    for text, meta, expected in cases:
        cat, rationale = inv.classify(
            Fault(step="s", error=RuntimeError(text), iteration=1,
                  metadata=meta))
        assert cat == expected, (text, cat)
        assert rationale


def test_goal_drift_pause_realign_resume():
    def drift_injector(iteration, plan):
        if iteration == 4:
            bad = copy.deepcopy(plan)
            for m in bad["milestones"][:2]:
                m["owner"] = None
                m["due"] = None
                m["next_action"] = None
            bad["sections"]["scope"] = "TODO"
            bad["budget"] = {"total": None, "breakdown": []}
            bad["stakeholders"] = bad["stakeholders"][:1]
            bad["evidence"] = []
            return bad
        return plan

    eng = ImprovementEngine(
        LoopConfig(task="t", quality_threshold=0.85, max_iterations=10,
                   drift_threshold=0.10, checkpoint_every=2, seed=SEED),
        drift_injector=drift_injector)
    rep = eng.run()
    assert len(rep.drift_events) >= 1
    ev = rep.drift_events[0]
    assert ev["regression"] > 0.10
    # after re-alignment the run still converges
    assert rep.termination == Termination.MET_STANDARD
    assert any(e["event"] == "drift_realigned" for e in rep.monitor)


def test_ledger_chain_integrity():
    ledger = AuditLedger()
    for i in range(10):
        ledger.append("evt", {"i": i})
    assert ledger.verify()
    assert ledger.count() == 10
    # tampering breaks verification
    ledger._entries[4]["payload"] = {"i": "tampered"}
    assert not ledger.verify()


def test_no_forbidden_names():
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    roots = [
        os.path.join(base, "src", "governed_agents", "improvement_loop"),
        os.path.join(base, "01-improvement-loop"),
        os.path.join(base, "examples", "01_improvement_loop_demo.py"),
    ]
    # Build the banned list from character codes so the literals never
    # appear in this file (otherwise the test would match its own pattern).
    def _w(*codes):
        return "".join(chr(c) for c in codes)
    banned = [_w(122, 101, 110, 105, 116, 104),
              _w(97, 105, 45, 103, 111, 115),
              _w(103, 111, 115),
              _w(102, 105, 115),
              _w(97, 122, 117, 114, 101)]
    pattern = re.compile(r"\b(%s)\b" % "|".join(banned), re.IGNORECASE)
    bad = []
    for root in roots:
        if os.path.isfile(root):
            paths = [root]
        else:
            paths = [os.path.join(dirpath, fn)
                     for dirpath, _, filenames in os.walk(root)
                     for fn in filenames
                     if fn.endswith((".py", ".md"))
                     and "__pycache__" not in dirpath]
        for p in paths:
            text = open(p, encoding="utf-8").read()
            for m in pattern.finditer(text):
                bad.append("%s: %s" % (p, m.group(0)))
    assert not bad, bad


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", name, "->", e)
    print("%d/%d passed" % (len(fns) - failed, len(fns)))
    sys.exit(1 if failed else 0)
