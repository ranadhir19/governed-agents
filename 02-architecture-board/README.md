# Architecture Board

A multi-agent advisory board for architecture decisions. Real decisions span
software, cloud, AI/ML, data, and agentic systems at once - trading off cost,
latency, scalability, robustness, integration, and simplicity - yet reviews are
usually single-domain and poorly recorded. This board fixes both: five domain
specialists score 44 architecture patterns against your 1-5 priorities, a
design critic stress-tests the combined blueprint (with an optimiser loop that
applies fixes), and a JSON-configurable policy checker enforces governance.
Missing critical information is reported on an explicit checklist, never
inferred.

## Problem

- Architecture reviews are single-domain; cross-layer interactions
  (edge serving vs. data tier, generative AI vs. PII policy) go unexamined.
- Decisions are poorly recorded: no ADR, no rationale, no alternatives.
- Missing inputs get silently inferred instead of flagged.
- Designs can be excellent yet non-compliant with architecture policy.

## Solution

A chief-architect orchestrator decomposes the requirement and routes
sub-briefs to five specialists (Software, Cloud, AI/ML, Data, Agentic
Systems). The board demonstrates the agentic patterns it recommends:
routing, orchestrator-workers, parallelisation (specialists score
concurrently), evaluator-optimiser (critic loop with pattern swaps), and a
shared blackboard. Each specialist scores its pattern catalogue on six
dimensions weighted by the requester's priorities; the critic checks for
over-engineering, conflicting combinations, resilience and consistency gaps;
the policy checker evaluates a JSON policy (model gateway, PII redaction,
tool governance, environment isolation, tamper-evident audit, approved
egress). Output: ranked patterns per layer, trade-off analysis, critic
findings, policy results, and a rendered Architecture Decision Record.

## Architecture

```
src/governed_agents/architecture_board/
  models.py        # Pattern, Requirement, Priorities, Finding, BoardResult
  patterns.py      # 44-pattern catalogue (9 software, 8 cloud, 9 ai_ml, 9 data, 9 agentic)
  specialists.py   # 5 specialists; numpy weighted scoring, seeded jitter
  blackboard.py    # shared coordination surface
  orchestrator.py  # ChiefArchitect: route -> parallel score -> critic loop -> policy -> ADR
  critic.py        # DesignCritic: over-engineering, conflicts, resilience, consistency
  policy.py        # PolicyChecker over JSON policy (DEFAULT_POLICY + load/save)
  inputs.py        # document parsing + missing-information checklist (never inferred)
  adr.py           # markdown ADR renderer
```

## How to run

```bash
cd 02-architecture-board
PYTHONPATH=../src python3 demo.py
```

Runs the seeded end-to-end demo (fraud-scoring brief), prints ranked patterns,
critic findings, policy results, the missing-info checklist, and the ADR, then
runs the two results experiments and writes `results/`.

## Results

Seed 7. Demo brief (10k req/s fraud scoring, PII in scope, PCI DSS):

- Blueprint: event-driven architecture, fully managed platform services,
  real-time inference endpoint (via optimiser swap), CDC streaming pipeline,
  router to specialist agents.
- Critic caught a retrieval-only AI/ML pick for a scoring task and the
  optimiser swapped in real-time inference; second pass clean (2 iterations).
- Policy: 3 violations (PII redaction, tool governance, approved egress),
  2 passes. Missing info: team size (reported, not inferred).

Experiments (`results/charts.png`, `results/results.md`):

1. Priority sensitivity: sweeping cost priority 1-5 depresses the fit of the
   latency-optimised top picks (cloud 7.57 -> 7.33); a rank flip appears in the
   software layer - the expected behaviour of priority weighting.
2. Critic/policy across three briefs: fraud 1 medium finding (resolved),
   trading 2 medium (both resolved via swaps), copilot 0; policy violations
   3 / 1 / 1. The critic and the policy checker catch different failure
   classes.

Honest limits: pattern scores are expert-judgement baselines, not
measurements; the critic is rule-based; the policy checker is only as strong
as the JSON policy it is given.
