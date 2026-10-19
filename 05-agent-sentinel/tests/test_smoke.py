"""Smoke tests for agent-sentinel (seeded, deterministic)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from governed_agents.agent_sentinel import (
    Agent,
    AgentRegistry,
    derive_contract,
    risk_tier,
    SimulatedFeed,
    learn_baselines,
    Scorer,
    HashChain,
    GateQueue,
    GateDecision,
    is_high_risk,
    CircuitBreaker,
    ContainmentController,
    EvalSuite,
    MonitoringBus,
    Event,
    FINDING_CATALOG,
)


def _agent(**kw):
    base = dict(agent_id="t-agent", role="test",
                data_classes=frozenset({"internal"}),
                tool_scopes=frozenset({"a.read"}),
                egress_allowlist=frozenset({"x.internal"}))
    base.update(kw)
    return Agent(**base)


def _event(**kw):
    base = dict(seq=1, ts=1.0, agent_id="t-agent", run_id="r1", kind="tool_call",
                tool="t", scope="a.read")
    base.update(kw)
    return Event(**base)


def test_rubric_tiers():
    assert risk_tier(0) == "low"
    assert risk_tier(2) == "moderate"
    assert risk_tier(3) == "high"
    assert risk_tier(6) == "critical"


def test_contract_derivation_low():
    c = derive_contract(_agent())
    assert c.risk_tier == "low" and c.risk_score == 0
    assert not c.human_gate_required
    assert c.max_actions_per_run == 200


def test_contract_derivation_critical():
    c = derive_contract(_agent(data_classes=frozenset({"pci"}), writes_production=True,
                               external_egress=True, autonomous=True, handles_secrets=True))
    assert c.risk_tier == "critical" and c.risk_score == 6
    assert c.human_gate_required
    assert c.max_actions_per_run == 20
    assert len(c.honeytokens) == 2


def test_budgets_tighten_with_risk():
    lows = derive_contract(_agent()).max_egress_bytes_per_run
    crits = derive_contract(_agent(data_classes=frozenset({"pci"}), writes_production=True,
                                   external_egress=True, autonomous=True,
                                   handles_secrets=True)).max_egress_bytes_per_run
    assert lows > crits


def test_registry_no_invented_agents():
    reg = AgentRegistry()
    assert len(reg) == 0
    reg.register(_agent(agent_id="a1"))
    assert [a["agent_id"] for a in reg.snapshot()] == ["a1"]


def test_baseline_excludes_rogue():
    feed = SimulatedFeed(seed=7)
    base = feed.baseline_window(n_per_agent=40)
    assert all(not e.rogue for e in base)
    baselines = learn_baselines(base)
    assert set(baselines) == {"doc-summarizer", "support-copilot", "data-analyst",
                              "code-reviewer", "payment-ops", "research-agent"}


def test_baseline_rejects_rogue_events():
    feed = SimulatedFeed(seed=7)
    _, rogues = feed.live_stream(n_per_agent=20)
    try:
        learn_baselines(rogues)
    except ValueError:
        return
    raise AssertionError("rogue events must be rejected from baseline learning")


def test_honeytoken_tripwire():
    reg = AgentRegistry()
    reg.register(_agent(agent_id="pay", data_classes=frozenset({"pci"}),
                        handles_secrets=True,
                        egress_allowlist=frozenset({"p.internal"})))
    contracts = {"pay": derive_contract(reg.get("pay"))}
    baselines = {"pay": learn_baselines(
        [ _event(agent_id="pay", kind="egress", dest="p.internal", bytes_out=100)
          for _ in range(5) ] )["pay"]}
    sc = Scorer(contracts, baselines)
    ev = _event(agent_id="pay", kind="egress", dest="evil.example.net", bytes_out=500,
                payload_markers=frozenset({"honeytoken:honey-apikey-pay"}))
    types = {f.finding_type for f in sc.score(ev)}
    assert "honeytoken_tripwire" in types
    assert "new_egress" in types
    assert "self_exfiltration" not in types  # no sensitive marker on this one


def test_new_egress_and_self_exfiltration():
    reg = AgentRegistry()
    reg.register(_agent(agent_id="pay", data_classes=frozenset({"pci"}),
                        egress_allowlist=frozenset({"p.internal"})))
    contracts = {"pay": derive_contract(reg.get("pay"))}
    baselines = {"pay": learn_baselines(
        [_event(agent_id="pay", kind="egress", dest="p.internal", bytes_out=100)
         for _ in range(5)])["pay"]}
    sc = Scorer(contracts, baselines)
    ev = _event(agent_id="pay", kind="egress", dest="evil.example.net", bytes_out=500,
                payload_markers=frozenset({"pci"}))
    types = {f.finding_type for f in sc.score(ev)}
    assert {"new_egress", "self_exfiltration"} <= types


def test_out_of_scope_tool():
    contracts = {"t-agent": derive_contract(_agent())}
    baselines = {"t-agent": learn_baselines(
        [_event(kind="tool_call", tool="t", scope="a.read") for _ in range(5)])["t-agent"]}
    sc = Scorer(contracts, baselines)
    types = {f.finding_type for f in sc.score(_event(kind="tool_call", tool="x", scope="b.admin"))}
    assert "out_of_scope_tool" in types


def test_prompt_injection():
    contracts = {"t-agent": derive_contract(_agent())}
    baselines = {"t-agent": learn_baselines(
        [_event(kind="tool_call", tool="t", scope="a.read") for _ in range(5)])["t-agent"]}
    sc = Scorer(contracts, baselines)
    ev = _event(kind="model_output", tool="t", scope="a.read",
                payload_markers=frozenset({"injection:ignore-prior"}))
    types = {f.finding_type for f in sc.score(ev)}
    assert "prompt_injection" in types


def test_data_ceiling_breach():
    contracts = {"t-agent": derive_contract(_agent())}  # ceiling 10000
    baselines = {"t-agent": learn_baselines(
        [_event(kind="data_access", records=3) for _ in range(5)])["t-agent"]}
    sc = Scorer(contracts, baselines)
    types = {f.finding_type for f in sc.score(_event(kind="data_access", records=20000))}
    assert "data_ceiling_breach" in types


def test_scorer_is_detect_only():
    for ftype, (sev, *_rest) in FINDING_CATALOG.items():
        assert sev in ("critical", "high")
    contracts = {"t-agent": derive_contract(_agent())}
    baselines = {"t-agent": learn_baselines(
        [_event(kind="tool_call", tool="t", scope="a.read") for _ in range(5)])["t-agent"]}
    sc = Scorer(contracts, baselines)
    for f in sc.score(_event(kind="tool_call", tool="x", scope="b.admin")):
        assert f.action == "detect_only"


def test_findings_mapped_to_frameworks():
    for ftype, (sev, tactic, technique, owasp_id, owasp_name) in FINDING_CATALOG.items():
        assert tactic and technique and owasp_id.startswith("LLM")


def test_hash_chain_integrity_and_tamper():
    ch = HashChain()
    ch.append("contract", {"a": 1}, ts=1.0)
    ch.append("finding", {"b": 2}, ts=2.0)
    ok, _ = ch.verify()
    assert ok and len(ch) == 2
    # tamper with an entry's payload: verification must fail
    ch._entries[0].data["a"] = 999
    ok, bad = ch.verify()
    assert not ok and bad == 0


def test_gate_hold_approve_deny():
    q = GateQueue()
    c = derive_contract(_agent(data_classes=frozenset({"pci"}), writes_production=True,
                               external_egress=True, autonomous=True, handles_secrets=True))
    ev = _event(agent_id="t-agent", kind="data_access", records=50)
    assert c.human_gate_required and is_high_risk(ev, c)
    h = q.hold(ev, "test")
    assert h.decision == GateDecision.HELD and q.pending()
    q.decide(h.gate_id, approve=True, approver="tester")
    assert h.decision == GateDecision.APPROVED
    h2 = q.hold(ev, "test2")
    q.decide(h2.gate_id, approve=False, approver="tester")
    assert h2.decision == GateDecision.DENIED
    assert not q.pending()


def test_circuit_breaker_trips_at_two_criticals():
    from governed_agents.agent_sentinel.scorer import Finding
    br = CircuitBreaker(threshold=2, window_seconds=600.0)

    def crit(ts):
        return Finding("honeytoken_tripwire", "critical", "a", 1, "r",
                       "Exfiltration", "Exfiltration via Cyber Means",
                       "LLM02", "Sensitive Information Disclosure", "d")

    def high(ts):
        return Finding("volume_spike", "high", "a", 2, "r",
                       "Exfiltration", "Exfiltration via Cyber Means",
                       "LLM10", "Unbounded Consumption", "d")

    assert not br.observe(high(0.0), 0.0)
    assert not br.observe(crit(10.0), 10.0)   # first critical: no trip
    assert br.observe(crit(20.0), 20.0)        # second critical: trip
    assert br.tripped("a")


def test_containment_requires_no_auto_action_and_is_reversible(tmp_path=None):
    import tempfile
    ch, mon = HashChain(), MonitoringBus()
    with tempfile.TemporaryDirectory() as d:
        cc = ContainmentController(ch, mon, os.path.join(d, "state.json"))
        inc = cc.propose("a", "test trigger", ts=1.0)
        assert not cc.egress_blocked("a")  # proposing alone changes nothing
        cc.confirm("a", inc, approver="human", ts=2.0)
        assert cc.egress_blocked("a") and cc.actions_blocked("a")
        # persisted
        cc2 = ContainmentController(ch, mon, os.path.join(d, "state.json"))
        assert cc2.egress_blocked("a")
        cc.release("a", approver="human", ts=3.0)
        assert not cc.egress_blocked("a")
        # every transition emitted monitoring events (never silent)
        assert len(mon.events("self_healing")) == 3


def test_eval_alarm_thresholds():
    suite = EvalSuite(seed=99)
    r1 = suite.run("x-agent", round=1)
    assert not suite.check_alarms(r1)
    r2 = suite.run("x-agent", round=2, capability_override=r1.capability + 18.0)
    alarms = suite.check_alarms(r2)
    assert len(alarms) == 1 and alarms[0].action == "return_to_intake"
    assert any("capability jump" in r for r in alarms[0].reasons)


def test_no_forbidden_names():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    # This test file itself names the forbidden strings; exclude it.
    files = [p for p in
             list((root / "src" / "governed_agents" / "agent_sentinel").rglob("*.py")) +
             list((root / "05-agent-sentinel").rglob("*.py"))
             if p.name != "test_smoke.py"]
    hits = []
    for p in files:
        text = p.read_text().lower()
        if "zenith" in text:
            hits.append((str(p), "zenith"))
        if re.search(r"(?<![a-z])gos(?![a-z])", text):
            hits.append((str(p), "gos"))
        if "fisglobal" in text or "fis" in re.findall(r"(?<![a-z])fis(?![a-z])", text):
            hits.append((str(p), "fis"))
        if re.search(r"(?<![a-z])azure(?![a-z])", text):
            hits.append((str(p), "azure"))
    assert not hits, hits


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
