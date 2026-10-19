# Architecture Board - Results

Seeded end-to-end runs (seed 7). All numbers below are produced by
`demo.py` (`run_demo` + `run_experiments`); re-running reproduces them exactly.
Charts: `charts.png`.

## Demo brief: real-time fraud scoring platform

Requirement: 10,000 req/s sustained (25,000 peak), p99 < 100ms, PII in scope
(cardholder data), PCI DSS, cloud, 99.95% availability. Team size deliberately
omitted to exercise the missing-information checklist. Priorities (1-5):
cost 2, latency 5, scalability 5, robustness 4, integration 3, simplicity 3.

### Ranked patterns (top pick per layer, fit /10)

| Layer | Chosen pattern | Fit |
|---|---|---|
| Software | Event-driven architecture | 6.91 |
| Cloud | Fully managed platform services | 7.50 |
| AI/ML | Real-time inference endpoint (via optimiser swap; ranked top was embedding-based semantic search at 7.67) | - |
| Data | Change-data-capture streaming pipeline | 7.18 |
| Agentic | Router to specialist agents | 6.85 |

### Evaluator-optimiser in action

- Critic pass 1 flagged 1 medium finding: the initial AI/ML top pick was
  **embedding-based semantic search** (fit 7.67), a retrieval-only pattern that
  cannot produce fraud *scores*. The optimiser swapped in **real-time inference
  endpoint**, and critic pass 2 was clean.
- Critic pass 2: 0 findings. 2 iterations, 1 blueprint revision.

### Policy compliance (policy.json)

- VIOLATION [high] pii-redaction: PII in scope, no guardrailed-generation pattern selected
- VIOLATION [high] agent-tool-governance: agentic router without guardrailed tool access
- VIOLATION [medium] approved-egress: outward-calling agent without gateway/tool-governance layer
- PASS env-isolation, tamper-evident-audit

### Missing-information checklist

- `team_size` was the only missing critical field; reported, never inferred.

## Experiment 1: priority-weighting sensitivity

Cost priority swept 1-5 (all other priorities fixed at demo values); fit of the
top-ranked pattern per layer:

| cost | software | cloud | ai_ml | data | agentic |
|---|---|---|---|---|---|
| 1 | 7.00 | 7.57 | 7.71 | 7.24 | 6.85 |
| 2 | 6.91 | 7.50 | 7.67 | 7.18 | 6.85 |
| 3 | 6.83 | 7.44 | 7.64 | 7.13 | 6.86 |
| 4 | 6.86 | 7.38 | 7.62 | 7.08 | 6.87 |
| 5 | 6.91 | 7.33 | 7.59 | 7.04 | 6.87 |

Read: the demo's top picks are latency/scalability-optimised, so weighting cost
more heavily depresses their weighted fit (cloud 7.57 -> 7.33, data 7.24 -> 7.04).
The kink in the software line at cost=3-5 marks a rank change: the top software
pattern flips as cost weight grows, which is exactly the behaviour a
priority-weighted board should exhibit. Agentic fit is nearly flat: the router
pattern is balanced across dimensions.

## Experiment 2: critic findings and policy violations across briefs

| Brief | Critic findings (first pass) | Remaining after optimiser | Policy violations | Critic iterations |
|---|---|---|---|---|
| fraud (real-time, PII) | 1 medium | 0 | 3 | 2 |
| global trading (ultra-low-latency) | 2 medium | 0 | 1 | 2 |
| support copilot (generative, PII) | 0 | 0 | 1 | 1 |

Notes:

- The trading brief triggered two consistency findings on the first pass
  (edge serving with a non-edge data tier; retrieval-only AI/ML for a
  prediction task). The optimiser applied both suggested swaps
  (CDC streaming -> feature store; embedding search -> real-time inference)
  and the second pass was clean.
- The support copilot brief is critic-clean with a single policy violation
  (PII without a redaction pattern). The critic checks architectural coherence;
  the policy checker checks governance - they catch different failure classes,
  which is why the board runs both.
- No high-severity critic findings appeared in these briefs; the over-engineering
  and conflict rules are covered by unit tests with adversarial blueprints.

## Honest limits

- Pattern scores are expert-judgement baselines (0-10), not measurements.
  Fit scores are only meaningful relative to each other within one run.
- The critic is rule-based; it catches known failure shapes, not novel ones.
- The policy checker evaluates the JSON policy it is given; a weak policy
  yields weak assurance. Policy rules are data so they can be hardened
  without code changes.
