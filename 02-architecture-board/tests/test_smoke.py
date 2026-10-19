"""Smoke tests for the architecture board (seeded, deterministic)."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import numpy as np

from governed_agents.architecture_board import (
    ChiefArchitect, PolicyChecker, Priorities, Requirement, all_specialists,
    check_missing, parse_document, total_patterns,
)
from governed_agents.architecture_board.critic import DesignCritic
from governed_agents.architecture_board.models import DIMENSIONS, Finding
from governed_agents.architecture_board.patterns import CATALOGUES, find_pattern
from governed_agents.architecture_board.policy import DEFAULT_POLICY, save_policy, load_policy

SEED = 7
HERE = os.path.dirname(os.path.abspath(__file__))


def _req(**kw):
    base = dict(title="T", problem="P", throughput="100 req/s",
                latency_budget="p99 < 200ms", data_sensitivity="none",
                compliance="none", team_size="10 engineers",
                budget_posture="moderate", deployment_target="cloud",
                availability_target="99.9%")
    base.update(kw)
    return Requirement(**base)


def test_catalogue_has_40_plus_patterns():
    assert total_patterns() >= 40, total_patterns()


def test_pattern_fields_complete():
    for domain, plist in CATALOGUES.items():
        assert len(plist) >= 8, (domain, len(plist))
        for p in plist:
            assert p.description and p.pros and p.cons, p.name
            assert p.when_to_use and p.poor_fit_when, p.name
            assert set(p.scores) == set(DIMENSIONS), p.name
            for d, s in p.scores.items():
                assert 0 <= s <= 10, (p.name, d, s)


def test_priorities_validated():
    try:
        Priorities(cost=6)
    except ValueError:
        pass
    else:
        raise AssertionError("cost=6 should raise")


def test_specialists_rank_full_catalogues():
    specs = all_specialists()
    assert len(specs) == 5
    rng = np.random.default_rng(SEED)
    for spec in specs:
        ranked = spec.score(_req(), Priorities(), rng)
        assert len(ranked) == len(spec.catalogue)
        fits = [s.fit for s in ranked]
        assert fits == sorted(fits, reverse=True)


def test_scoring_deterministic_across_runs():
    req, pri = _req(), Priorities(cost=2, latency=5)
    a = ChiefArchitect(seed=SEED).run(req, pri)
    b = ChiefArchitect(seed=SEED).run(req, pri)
    for d in a.ranked:
        assert [s.pattern.name for s in a.ranked[d]] == \
               [s.pattern.name for s in b.ranked[d]], d


def test_blueprint_covers_all_domains():
    res = ChiefArchitect(seed=SEED).run(_req(), Priorities())
    assert set(res.blueprint) == {"software", "cloud", "ai_ml", "data", "agentic"}
    assert len(res.workflow_log) > 5


def test_missing_info_reported_never_inferred():
    full = _req()
    assert check_missing(full) == []
    sparse = Requirement(title="T", problem="P")
    missing = check_missing(sparse)
    assert len(missing) == 8
    assert any(m.startswith("throughput") for m in missing)


def test_parse_document_extracts_fields():
    doc = ("Fraud scoring at 10,000 req/s, p99 under 100ms. Cardholder PII in "
           "scope, PCI DSS applies. Cloud deployment, 99.95% availability, team of 12.")
    req, notes = parse_document(doc)
    assert "10,000" in (req.throughput or "")
    assert "100ms" in (req.latency_budget or "")
    assert "PII" in (req.data_sensitivity or "")
    assert req.compliance == "PCI DSS"
    assert req.deployment_target == "cloud"
    assert "12" in (req.team_size or "")
    # team_size found -> not on the missing list; budget_posture not found -> is
    missing = check_missing(req)
    assert not any(m.startswith("team_size") for m in missing)
    assert any(m.startswith("budget_posture") for m in missing)


def test_policy_flags_missing_model_gateway():
    blueprint = {
        "software": find_pattern("Event-driven architecture"),
        "cloud": find_pattern("Fully managed platform services"),
        "ai_ml": find_pattern("Retrieval-augmented generation (RAG)"),
        "data": find_pattern("Change-data-capture streaming pipeline"),
        "agentic": find_pattern("Router to specialist agents"),
    }
    req = _req(data_sensitivity="PII in scope")
    results = PolicyChecker().check(blueprint, req)
    by_id = {r.rule_id: r for r in results}
    assert not by_id["genai-model-gateway"].passed
    assert not by_id["pii-redaction"].passed


def test_policy_passes_with_mitigations():
    blueprint = {
        "software": find_pattern("Event-driven architecture"),
        "cloud": find_pattern("Fully managed platform services"),
        "ai_ml": find_pattern("Guardrailed generation"),
        "data": find_pattern("Change-data-capture streaming pipeline"),
        "agentic": find_pattern("Guardrailed tool access"),
    }
    req = _req(data_sensitivity="PII in scope")
    results = PolicyChecker().check(blueprint, req)
    by_id = {r.rule_id: r for r in results}
    # gateway still missing -> violation; pii satisfied; tool governance not triggered
    # (Guardrailed tool access is selected, so no violation is reported)
    assert not by_id["genai-model-gateway"].passed
    assert by_id["pii-redaction"].passed
    assert by_id.get("agent-tool-governance", None) is None or \
        by_id["agent-tool-governance"].passed


def test_policy_json_roundtrip(tmp_path=None):
    path = os.path.join(HERE, "..", "policy.json")
    assert os.path.exists(path)
    policy = load_policy(path)
    assert len(policy["rules"]) == len(DEFAULT_POLICY["rules"])
    tmp = "/tmp/_policy_rt.json"
    save_policy(policy, tmp)
    assert load_policy(tmp) == policy


def test_critic_finds_overengineering():
    blueprint = {
        "software": find_pattern("Microservices"),
        "cloud": find_pattern("Multi-region active-active"),
        "ai_ml": find_pattern("Supervised fine-tuning"),
        "data": find_pattern("Data mesh"),
        "agentic": find_pattern("Multi-agent debate and consensus"),
    }
    findings = DesignCritic().evaluate(blueprint, _req())
    oe = [f for f in findings if f.category == "over-engineering"]
    assert oe and oe[0].severity == "high"
    assert oe[0].suggested_swap  # optimiser has something to apply


def test_critic_finds_conflict_pair():
    blueprint = {
        "software": find_pattern("Modular monolith"),
        "cloud": find_pattern("Multi-region active-active"),
        "ai_ml": find_pattern("Embedding-based semantic search"),
        "data": find_pattern("Central data warehouse"),
        "agentic": find_pattern("Single ReAct agent"),
    }
    findings = DesignCritic().evaluate(blueprint, _req())
    assert any(f.category == "conflict" and f.severity == "high" for f in findings)


def test_optimiser_loop_applies_swap():
    req = Requirement(
        title="Fraud scoring", problem="Score transactions for fraud in real time.",
        throughput="10,000 req/s", latency_budget="p99 < 100ms",
        data_sensitivity="PII in scope", compliance="PCI DSS",
        budget_posture="moderate", deployment_target="cloud",
        availability_target="99.95%")
    pri = Priorities(cost=2, latency=5, scalability=5, robustness=4,
                     integration=3, simplicity=3)
    res = ChiefArchitect(seed=SEED).run(req, pri)
    assert res.critic_iterations >= 1
    assert len(res.blueprint_history) >= 1
    # the retrieval-only mismatch must have been caught on the first pass
    assert any(f.category == "consistency" for f in res.initial_findings)


def test_adr_contains_required_sections():
    res = ChiefArchitect(seed=SEED).run(_req(), Priorities())
    adr = res.adr_markdown
    for section in ["## Context", "## Decision", "## Alternatives considered",
                    "## Trade-off analysis", "## Critic findings",
                    "## Policy compliance", "## Missing information",
                    "## Consequences", "## References"]:
        assert section in adr, section


def test_no_forbidden_names():
    root = os.path.join(os.path.dirname(__file__), "..", "..", "src",
                        "governed_agents", "architecture_board")
    bad = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith((".py", ".json", ".md")):
                text = open(os.path.join(dirpath, fn), encoding="utf-8").read()
                for pat in [r"\bZenith\w*\b", r"\bGOS\b", r"\bAI-GOS\b",
                            r"\bFIS\b", r"\bAzure\b"]:
                    if re.search(pat, text, re.IGNORECASE):
                        bad.append((fn, pat))
    assert not bad, bad
