"""Smoke tests for the expert council (application 3 of the governed-agents portfolio)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from governed_agents.expert_council import (
    AGENT_PATTERNS, CURRICULUM, DEMO_QUESTIONS, EXPERTS,
    Critic, Expert, KnowledgeGraph, Registry, Trainer,
    classify, parse_material, route, synthesise,
)
from governed_agents.expert_council.parse import tokenize

BANNED = ["zenith", "gos", "fis", "azure", "claude"]

TEXT = """TITLE: Leakage study
ABSTRACT: We study train test split hygiene and cross validation.
CLAIMS: A new baseline protocol.
METHODS: We compare against a baseline with an ablation study. No baseline is missing.
"""


def test_parse_extracts_sections():
    m = parse_material(TEXT)
    assert m["title"].startswith("Leakage"), m["title"][:30]
    assert "cross validation" in m["abstract"]
    assert len(m["tokens"]) > 10


def test_tokenize_splits_hyphenated():
    toks = tokenize("fine-tuning the model")
    assert "fine" in toks and "tuning" in toks


def test_classify_touches_aiml():
    m = parse_material(TEXT)
    c = classify(m, EXPERTS)
    ids = [d["id"] for d in c["touched"]]
    assert "aiml" in ids
    assert c["all"][0]["score"] >= c["all"][-1]["score"]


def test_route_returns_experts_capped():
    m = parse_material(TEXT)
    c = classify(m, EXPERTS)
    by_id = {s["id"]: Expert(s) for s in EXPERTS}
    routed = route(c, by_id, threshold=0.18, top_k=6)
    assert 1 <= len(routed) <= 6
    assert all(isinstance(e, Expert) for e, _, _ in routed)


def test_opinion_shape_and_verdicts():
    m = parse_material(TEXT)
    expert = Expert(next(s for s in EXPERTS if s["id"] == "aiml"))
    op = expert.opine(m)
    assert set(op) >= {"lenses", "risks", "references", "context"}
    assert all(l["verdict"] in ("addressed", "partial", "unaddressed") for l in op["lenses"])
    assert len(op["references"]) == 2


def test_risk_flag_fires_on_trigger():
    m = parse_material("TITLE: t\nABSTRACT: We train on test data. METHODS: train on test.")
    expert = Expert(next(s for s in EXPERTS if s["id"] == "aiml"))
    op = expert.opine(m)
    names = [r["risk"] for r in op["risks"]]
    assert "data leakage" in names


def test_verdict_dimensions_and_recommendation():
    m = parse_material(TEXT)
    by_id = {s["id"]: Expert(s) for s in EXPERTS}
    c = classify(m, EXPERTS)
    routed = route(c, by_id, threshold=0.18, top_k=6)
    opinions = [e.opine(m) for e, _, _ in routed]
    vocab = set(w for s in EXPERTS for cpt in s["concepts"] for w in cpt.split())
    v = synthesise(m, opinions, vocab)
    assert set(v["dimensions"]) == {"Novelty", "Rigour", "Feasibility", "Impact",
                                    "Governance-fit", "Risk"}
    assert all(0 <= x <= 10 for x in v["dimensions"].values())
    assert v["recommendation"] in ("accept", "revise", "reject")


def test_registry_append_only_and_chain():
    r = Registry()
    r.append("aiml", "opinion", {"a": 1})
    r.append("aiml", "training", {"b": 2})
    assert len(r.for_expert("aiml")) == 2
    assert r.verify()
    # tamper -> detected
    r.entries[0]["payload"] = {"a": 999}
    assert not r.verify()


def test_critic_grades_valid():
    critic = Critic()
    expert = Expert(next(s for s in EXPERTS if s["id"] == "gov"))
    s = critic.score(expert)
    assert set(s["dimensions"]) == {"breadth", "depth", "grounding", "vigilance", "cultivation"}
    assert 0.0 <= s["overall"] <= 1.0
    assert s["grade"] in ("Novice", "Practitioner", "Senior", "Principal")


def test_trainer_improves_and_consumes_curriculum():
    experts = [Expert(s) for s in EXPERTS]
    critic = Critic()
    reg = Registry()
    trainer = Trainer(CURRICULUM, critic, reg)
    before = [critic.score(e)["overall"] for e in experts]
    reports = trainer.cycle(experts)
    after = [critic.score(e)["overall"] for e in experts]
    assert all(a >= b for a, b in zip(after, before))
    assert sum(1 for r in reports if r["trained"]) == len(experts)
    assert reg.verify()


def test_kg_retrieve_and_answer_modes():
    kg = KnowledgeGraph(EXPERTS, AGENT_PATTERNS)
    hits = kg.retrieve(DEMO_QUESTIONS[0])
    assert len(hits) > 0
    a1 = kg.answer(DEMO_QUESTIONS[0])
    assert a1["mode"] == "grounded-synthesis"
    assert a1["answer"] and isinstance(a1["citations"], list)
    a2 = kg.answer(DEMO_QUESTIONS[1], llm=lambda p: "canned")
    assert a2["mode"] == "llm-augmented" and a2["answer"] == "canned"


def test_no_banned_names_in_package():
    root = os.path.join(os.path.dirname(__file__), "..", "..", "src",
                        "governed_agents", "expert_council")
    hits = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py"):
                text = open(os.path.join(dirpath, fn)).read().lower()
                for b in BANNED:
                    if b in text:
                        hits.append((fn, b))
    assert not hits, hits


def test_demo_questions_ready_made():
    assert len(DEMO_QUESTIONS) >= 2
    kg = KnowledgeGraph(EXPERTS, AGENT_PATTERNS)
    for q in DEMO_QUESTIONS:
        assert len(kg.retrieve(q)) > 0
