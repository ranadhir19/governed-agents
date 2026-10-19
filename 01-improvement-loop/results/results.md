# Improvement loop: results (seed 7)

## Configuration

| setting | value |
|---|---|
| task | Draft a project plan for migrating the analytics pipeline |
| quality_threshold | 0.85 |
| max_iterations | 12 |
| budget | 60.0 |
| cost_per_iteration | 5.0 |
| plateau_k | 3 |
| checkpoint_every | 2 |
| human_gates | (6,) |
| drift_threshold | 0.1 |
| seed | 7 |

## Main scenario: termination `met_standard` after 7 iterations

| iteration | composite | best so far | event |
|---|---|---|---|
| 1 | 0.217 | 0.217 |  |
| 2 | 0.516 | 0.516 |  |
| 3 | 0.793 | 0.793 | resource fault injected; healed (verified) |
| 4 | 0.729 | 0.793 |  |
| 5 | 0.686 | 0.793 | goal drift detected (regression 0.108); re-aligned from checkpoint |
| 6 | 0.807 | 0.807 | human gate approved |
| 7 | 0.960 | 0.960 |  |

## Headline numbers

- Iterations to convergence: **7** (termination: `met_standard`)
- Best composite score: **0.960** (standard: 0.85)
- Budget spent: **35.0** of 60.0 (25.0 left)
- Faults injected: **1**; recovered: **1**; verified: **1**
  - classified `resource` (resource pressure signature in fault text); lesson kept: "quarantine failing step; halve the work unit and retry with backoff"
- Goal-drift events: **1** (regression 0.108 > threshold 0.1); re-aligned and resumed
- Checkpoints taken: **3**; human gates: [{'iteration': 6, 'approved': True}]
- Audit ledger: **22** entries, chain intact: **True**
- Lessons retained: **1**

## Plateau behaviour (secondary run)

- With an unsatisfiable domain requirement capping the composite below the 1.00 standard, the loop terminated `plateau` after 8 iterations with no improvement over the last 3 (best 0.800).

## Budget exhaustion (secondary run)

- With budget 12.0 at 5.0/iteration, the loop terminated `budget_exhausted` after 3 iterations (10.0 spent).

All numbers above are from actual seeded runs (seed 7).
