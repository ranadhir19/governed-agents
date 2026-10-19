"""End-to-end demo: assess a synthetic proposal, cultivate the council,
answer grounded questions. Seeded; every number comes from a real run."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.expert_council import (
    AGENT_PATTERNS, CURRICULUM, DEMO_QUESTIONS, EXPERTS,
    Critic, Expert, KnowledgeGraph, Registry, Trainer,
    classify, parse_material, route, synthesise,
)

SEED = 7
rng = np.random.RandomState(SEED)

PROPOSAL = """TITLE: Federated Fine-Tuning of Language Models with Differential Privacy for Fraud Detection
ABSTRACT: We propose a federated fine-tuning pipeline that adapts a pretrained
language model to transaction-narrative fraud detection across three banks
without pooling raw data. Differential privacy budgeting bounds per-client
leakage, and a central orchestrator coordinates planning loop rounds with
tool use for feature extraction. A held-out test set per bank measures
generalisation; cross validation guides hyperparameter tuning.
CLAIMS: First application of differentially private federated fine-tuning to
multi-bank fraud narratives. We expect a 12 percent reduction in false
positives over the current rule baseline, with formal privacy guarantees.
METHODS: Each bank fine tunes a local adapter on its transaction narratives
using instruction tuning. Data lineage is tracked from source to training
example; label noise is estimated via annotator agreement. We report a single
seed pilot on 40k transactions with a train test split. The model card
documents limitations. Training uses proprietary data under NDA. A canary
deployment with rollback and model monitoring for drift detection is planned.
RISKS: No incident response plan is documented yet. A threat model for prompt
injection via transaction narratives is in draft.
"""

FILLER = ("This work builds on established practice. Results are reported "
          "transparently. The approach is designed for production use.")


def build_council():
    registry = Registry()
    experts = [Expert(spec) for spec in EXPERTS]
    return registry, experts


def assess(registry, experts):
    material = parse_material(PROPOSAL)
    classification = classify(material, EXPERTS)
    by_id = {e.id: e for e in experts}
    routed = route(classification, by_id, threshold=0.18, top_k=6)
    opinions = []
    for expert, score, hits in routed:
        op = expert.opine(material)
        opinions.append(op)
        registry.append(expert.id, "opinion",
                        {"routed_score": score, "lenses": len(op["lenses"]),
                         "risks": len(op["risks"]), "refs": len(op["references"])})
    vocab = set()
    for spec in EXPERTS:
        for c in spec["concepts"]:
            vocab.update(c.split())
    verdict = synthesise(material, opinions, vocab)
    return material, classification, routed, opinions, verdict


def print_assessment(classification, routed, opinions, verdict):
    print("== Classification ==")
    for d in classification["touched"]:
        print("  %-28s score=%.3f hits=%d" % (d["name"], d["score"], len(d["hits"])))
    print("\n== Routed experts: %d ==" % len(routed))
    for expert, score, hits in routed:
        print("  %s (%.3f)" % (expert.name, score))
    print("\n== Opinions ==")
    for op in opinions:
        addr = sum(1 for l in op["lenses"] if l["verdict"] == "addressed")
        print("\n[%s] lenses %d/%d addressed, %d risk(s) flagged" % (
            op["expert_name"], addr, len(op["lenses"]), len(op["risks"])))
        for l in op["lenses"]:
            if l["verdict"] != "addressed":
                print("    (%s) %s" % (l["verdict"], l["lens"][:80]))
        for r in op["risks"]:
            print("    [!%s] %s - %s" % (r["severity"], r["risk"], r["note"][:70]))
        print("    context: %s" % op["context"][:160])
        for ref in op["references"]:
            print("    ref: %s (%s, %d)" % (ref["title"], ref["venue"], ref["year"]))
    print("\n== Merit verdict ==")
    for dim, val in verdict["dimensions"].items():
        print("  %-14s %d/10" % (dim, val))
    print("  mean=%.2f recommendation=%s critical_risks=%d" % (
        verdict["mean"], verdict["recommendation"].upper(), verdict["critical_risks"]))
    print("  citations: %d" % len(verdict["citations"]))


def cultivate(registry, experts, opinions, cycles=3):
    history = {}
    for op in opinions:
        history.setdefault(op["expert_id"], []).append(op)
    critic = Critic(history)
    trainer = Trainer(CURRICULUM, critic, registry)
    checkpoints = []
    start = {e.id: critic.score(e) for e in experts}
    checkpoints.append(start)
    print("\n== Cultivation ==")
    print("cycle 0 (initial):")
    for e in experts:
        s = start[e.id]
        print("  %-28s overall=%.3f grade=%s" % (e.name, s["overall"], s["grade"]))
    for c in range(1, cycles + 1):
        reports = trainer.cycle(experts)
        snap = {e.id: critic.score(e) for e in experts}
        checkpoints.append(snap)
        improved = sum(1 for r in reports if r.get("trained") and r["after"] > r["before"])
        print("cycle %d: %d/8 experts improved" % (c, improved))
        for e in experts:
            s = snap[e.id]
            print("  %-28s overall=%.3f grade=%s" % (e.name, s["overall"], s["grade"]))
    print("registry entries: %d, chain valid: %s" % (len(registry.entries), registry.verify()))
    return checkpoints


def qa_demo():
    kg = KnowledgeGraph(EXPERTS, AGENT_PATTERNS)
    print("\n== Knowledge-graph Q&A ==")
    q1 = DEMO_QUESTIONS[0]
    a1 = kg.answer(q1)
    print("\nQ: %s\nmode: %s\n%s" % (q1, a1["mode"], a1["answer"][:900]))
    print("citations: %d" % len(a1["citations"]))

    def stub_llm(prompt):
        return ("Based on the grounded context, the recommended controls are: "
                "publish a model card, run a documented risk assessment, keep a "
                "human in the loop for high-stakes actions, adversarially test "
                "for prompt injection, apply least-privilege tool permissions, "
                "and maintain an incident response plan. [stub-llm]")

    q2 = DEMO_QUESTIONS[1]
    a2 = kg.answer(q2, llm=stub_llm)
    print("\nQ: %s\nmode: %s\nA: %s" % (q2, a2["mode"], a2["answer"][:400]))
    print("citations: %d (%s)" % (len(a2["citations"]), "; ".join(a2["citations"][:3])))
    return kg


# -- routing precision experiment -------------------------------------------
def routing_experiment(n=24):
    by_id = {s["id"]: s for s in EXPERTS}
    rng2 = np.random.RandomState(123)
    y_true, y_pred = {s["id"]: [] for s in EXPERTS}, {s["id"]: [] for s in EXPERTS}
    for i in range(n):
        ids = list(by_id)
        k = 2 if rng2.rand() < 0.3 else 1
        true_ids = list(rng2.choice(ids, size=k, replace=False))
        concepts = []
        for tid in true_ids:
            pool = by_id[tid]["concepts"]
            concepts += list(rng2.choice(pool, size=min(6, len(pool)), replace=False))
        # distractors: concepts from unrelated domains
        others = [eid for eid in ids if eid not in true_ids]
        for did in rng2.choice(others, size=2, replace=False):
            pool = by_id[did]["concepts"]
            concepts += list(rng2.choice(pool, size=2, replace=False))
        rng2.shuffle(concepts)
        text = ("TITLE: synthetic brief %d\nABSTRACT: %s\nMETHODS: %s\n%s"
                % (i, " ".join(concepts[:8]), " ".join(concepts[8:]), FILLER))
        material = parse_material(text)
        classification = classify(material, EXPERTS)
        pred_ids = [d["id"] for d in classification["touched"][:6] if d["score"] >= 0.18]
        for eid in ids:
            y_true[eid].append(1 if eid in true_ids else 0)
            y_pred[eid].append(1 if eid in pred_ids else 0)
    per_expert = {}
    for eid in by_id:
        tp = sum(1 for t, p in zip(y_true[eid], y_pred[eid]) if t and p)
        fp = sum(1 for t, p in zip(y_true[eid], y_pred[eid]) if not t and p)
        fn = sum(1 for t, p in zip(y_true[eid], y_pred[eid]) if t and not p)
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, tp + fn)
        f1 = 2 * prec * rec / max(1e-9, prec + rec)
        per_expert[eid] = {"precision": round(prec, 3), "recall": round(rec, 3),
                           "f1": round(f1, 3)}
    return per_expert


def save_charts(per_expert, checkpoints, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ids = [s["id"] for s in EXPERTS]
    x = np.arange(len(ids))
    w = 0.25
    axes[0].bar(x - w, [per_expert[i]["precision"] for i in ids], w, label="precision")
    axes[0].bar(x, [per_expert[i]["recall"] for i in ids], w, label="recall")
    axes[0].bar(x + w, [per_expert[i]["f1"] for i in ids], w, label="F1")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(ids, rotation=30, ha="right")
    axes[0].set_ylim(0, 1.05)
    axes[0].set_title("Routing precision/recall/F1 per expert (n=24 labelled)")
    axes[0].legend()

    for spec in EXPERTS:
        series = [checkpoints[c][spec["id"]]["overall"] for c in range(len(checkpoints))]
        axes[1].plot(range(len(checkpoints)), series, marker="o",
                     label=spec["id"], alpha=0.8)
    axes[1].set_xticks(range(len(checkpoints)))
    axes[1].set_xlabel("cultivation cycle")
    axes[1].set_ylabel("critic overall score")
    axes[1].set_title("Expert critic scores across 3 cultivation cycles")
    axes[1].legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print("saved", out)


def main():
    registry, experts = build_council()
    material, classification, routed, opinions, verdict = assess(registry, experts)
    print_assessment(classification, routed, opinions, verdict)
    checkpoints = cultivate(registry, experts, opinions, cycles=3)
    qa_demo()
    per_expert = routing_experiment()
    mp = sum(v["precision"] for v in per_expert.values()) / 8
    mr = sum(v["recall"] for v in per_expert.values()) / 8
    mf = sum(v["f1"] for v in per_expert.values()) / 8
    print("\n== Routing experiment (n=24) ==")
    print("mean precision=%.3f recall=%.3f F1=%.3f" % (mp, mr, mf))
    out = os.path.join(os.path.dirname(__file__), "results", "charts.png")
    save_charts(per_expert, checkpoints, out)
    with open(os.path.join(os.path.dirname(__file__), "results", "results.md"), "w") as f:
        f.write(results_md(verdict, routed, per_expert, mp, mr, mf, checkpoints, registry))


def results_md(verdict, routed, per_expert, mp, mr, mf, checkpoints, registry):
    lines = ["# 03-expert-council: results (seed 7)", ""]
    lines.append("## Demo proposal verdict")
    for dim, val in verdict["dimensions"].items():
        lines.append("- %s: %d/10" % (dim, val))
    lines += ["- mean: %.2f" % verdict["mean"],
              "- recommendation: %s" % verdict["recommendation"],
              "- experts routed: %d" % len(routed),
              "- citations: %d" % len(verdict["citations"]), ""]
    lines.append("## Routing precision (24 synthetic labelled briefs, seed 123)")
    lines.append("Limitation: briefs are generated from the same concept vocabulary "
                 "the classifier uses, so scores measure routing machinery, not "
                 "real-world generalisation.")
    for eid, v in per_expert.items():
        lines.append("- %s: P=%.3f R=%.3f F1=%.3f" % (eid, v["precision"], v["recall"], v["f1"]))
    lines.append("- mean: P=%.3f R=%.3f F1=%.3f" % (mp, mr, mf))
    lines.append("")
    lines.append("## Cultivation (critic overall per expert)")
    for spec in EXPERTS:
        series = [checkpoints[c][spec["id"]]["overall"] for c in range(len(checkpoints))]
        grades = [checkpoints[c][spec["id"]]["grade"] for c in range(len(checkpoints))]
        lines.append("- %s: %s (grades %s -> %s)" % (
            spec["id"], " -> ".join("%.3f" % s for s in series), grades[0], grades[-1]))
    lines += ["", "- registry entries: %d" % len(registry.entries),
              "- audit chain valid: %s" % registry.verify()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
