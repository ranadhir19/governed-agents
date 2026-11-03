# 03 — Expert Council

An orchestrated multi-agent expert reference system: a general, open
implementation of the "in-house reference brain" concept. Eight domain
experts with curated knowledge bases read material, add context, produce a
defensible merit analysis with citations, and keep improving through
continuous cultivation. A knowledge graph supports grounded Q&A with or
without an attached language model.

No proprietary names, no cloud or vendor dependencies: standard library +
numpy, fully deterministic and seeded. A language model is an optional
`prompt -> text` callable, never a requirement.

## Problem

Some decisions need deep technical judgement across domains at once —
assessing a research paper, a proposal, a complex topic. Expert reviewers
are scarce, their reasoning is hard to audit, and a generic language-model
answer is ungrounded and cites nothing.

## Solution

1. **Council of eight experts** — AI/ML, Foundation Models/LLMs, Data
   Engineering & Science, AI Governance/Risk/Compliance, Technical &
   Systems Architecture, AI Security & Privacy, Agents & Multi-Agent
   Systems, MLOps & Platform. Each carries a curated knowledge base:
   concepts, evaluation lenses ("is the train/test split leakage-free?"),
   risk-flag patterns (no baseline, data leakage, benchmark contamination,
   hallucination, prompt injection, ...), canonical references.
2. **Understand** — parse the material (title, abstract, claims, methods,
   concepts) and classify which domains it touches.
3. **Orchestrate** — route the material only to relevant experts. Each
   returns an opinion: lenses answered with evidence, risks flagged,
   references cited, added context.
4. **Synthesise a merit verdict** — scored on six dimensions (Novelty,
   Rigour, Feasibility, Impact, Governance-fit, Risk) with an
   accept / revise / reject recommendation and citations.
5. **Continuous cultivation** — an append-only expert registry with a
   hash-chained audit log; a Critic scores every expert on breadth, depth,
   grounding, vigilance and cultivation and grades Novice -> Practitioner ->
   Senior -> Principal; a Trainer advances each expert by one curated
   curriculum item per cycle, weakest dimension first.
6. **Knowledge-graph-augmented Q&A** — experts, concepts, lenses, risks,
   references and an agent-architecture pattern catalogue form a small
   knowledge graph. Questions retrieve the most relevant grounded knowledge
   into an augmented brief; with a language model attached it answers with
   citations, without one it falls back to deterministic grounded synthesis.

## Architecture

```
src/governed_agents/expert_council/
  knowledge.py   curated KBs: 8 experts, agent pattern catalogue, curriculum
  parse.py       structured material parser (TITLE:/ABSTRACT:/CLAIMS:/METHODS:)
  classify.py    domain coverage classifier
  router.py      route only to relevant experts
  experts.py     Expert.opine() -> lenses, risks, references, context
  verdict.py     six-dimension merit synthesis + recommendation
  registry.py    append-only hash-chained audit log
  critic.py      five-dimension scoring + grades
  trainer.py     weakest-first curriculum advancement
  kg.py          knowledge graph + retrieval + Q&A (LLM optional)
```

## How to run

```bash
PYTHONPATH=src python3 03-expert-council/demo.py
PYTHONPATH=src python3 examples/03_expert_council_demo.py
```

The demo (seed 7): assesses a synthetic research proposal (federated
fine-tuning with differential privacy for fraud detection), prints
per-expert opinions and the merit verdict, runs 3 cultivation cycles,
answers 2 knowledge-graph questions, and writes `results/results.md` and
`results/charts.png`.

Tests:

```bash
PYTHONPATH=src python3 -m pytest 03-expert-council/tests/ -q
# (or run test_smoke.py functions directly; 13 tests, no pytest required)
```

## Results (seeded runs)

Demo proposal verdict: Novelty 9, Rigour 5, Feasibility 6, Impact 5,
Governance-fit 4, Risk 3 (all /10); mean 5.33, recommendation **REVISE**,
6 experts routed, 12 citations. The council correctly flagged undisclosed
training data and label-noise risk, and noted missing ablations and
unmodelled inference costs.

Routing precision on 24 synthetic labelled briefs (seed 123; briefs use
the same concept vocabulary as the classifier, so this measures the
routing machinery, not real-world generalisation): mean precision 0.729,
recall 1.000, F1 0.810. Recall is perfect; precision losses come from
distractor concepts pulling in adjacent experts — the router errs toward
over-consultation, which is the safe direction for a review council.

Cultivation over 3 cycles (critic overall, all 8 experts):
Practitioner (0.49-0.52) -> Senior (0.55-0.58) -> Senior (0.60-0.64) ->
Senior (0.66-0.69). Every expert improved every cycle (8/8); none has
reached Principal, which requires sustained cultivation (6+ items).

Registry: 30 entries, hash chain verifies clean.

## Limitations

- Opinions are keyword-grounded heuristics, not real expert judgement;
  lens verdicts depend on explicit textual evidence.
- The verdict dimensions are transparent heuristics (documented in
  `verdict.py`), not a substitute for human review.
- Routing and Q&A retrieval share the KB vocabulary; paraphrased or
  adversarial phrasing will degrade them.
