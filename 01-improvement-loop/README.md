# 01 — Improvement Loop: autonomous critic-gated refinement

## Problem

Long-running agents are usually improved the slow way: a person reads the
output, writes a better prompt, and re-runs — once per iteration. That does
not scale to overnight runs, and the quality bar drifts with whoever happens
to be prompting.

## Solution

Set the task, quality standard, budget and human gates **once up front**.
An orchestrator then drives `propose -> critique -> diagnose -> revise ->
repeat` with no per-iteration prompting:

- **Critic panel** — six generic critics (completeness, rigour, grounding,
  clarity, safety, actionability), each owning a requirements checklist and
  scoring the fraction of items satisfied against its own pass threshold.
  One weighted composite score. Domain critics plug in via `register`.
- **Diagnostician + reviser** — the critique becomes concrete directives
  aimed at the weakest dimensions first; the reviser applies them. Both the
  proposer and reviser are pluggable (`prompt -> text` callables for real
  LLM use); deterministic seeded defaults keep runs reproducible.
- **Long-run machinery** — bounded autonomy (max iterations / budget),
  best-so-far retention, plateau detection (no improvement over k
  iterations), checkpoint/resume, human gates, an append-only hash-chained
  audit ledger, and an explicit termination reason: `met_standard |
  plateau | budget_exhausted | halted_by_human`.
- **Self-healing** — a fault quarantines the failing step; an Investigator
  classifies the root cause (resource, logic, configuration, dependency,
  transient); the matching fix strategy runs; the plan is reorganised;
  recovery is verified; the fix is kept as a reusable lesson. Goal drift
  (objective regressing past a threshold) pauses the loop for diagnosis
  and re-alignment from checkpoint.
- **Safe checkpoints (memento)** — state is classified before capture:
  *Restore* (progress markers, best-so-far; written back), *Anchor*
  (ledger head hash + count; proves no rewind, never written back),
  *Rebuild* (derived data; never captured, recipe recorded instead).
  Unhealthy checkpoints are provisional and never restore targets.
  Rollback is allowed only for resource/logic faults — never configuration
  (could reinstate a revoked secret), dependency, or transient.

## Architecture

```
LoopConfig (task, standard, budget, gates, seed)
        |
propose -> critique -> diagnose -> revise -> repeat
   |          |           |           |
   |     CriticPanel  Diagnostician  Reviser (pluggable)
   |     (6 critics,                (deterministic,
   |      weighted composite)        capability-limited)
   |
   +-- AuditLedger (hash-chained, append-only)
   +-- CheckpointManager (Restore/Anchor/Rebuild, health gate)
   +-- Healer + Investigator (classify -> fix -> verify -> lesson)
   +-- GoalDriftMonitor (pause -> diagnose -> re-align -> resume)
   +-- human gates (approver hook; denial -> halted_by_human)
```

## How to run

```bash
cd 01-improvement-loop
PYTHONPATH=../src python3 demo.py        # full scenario -> results/
PYTHONPATH=../src python3 -m pytest tests/ -q   # or run test_smoke.py directly
```

The demo improves a synthetic project plan over 7 iterations (seed 7),
injects a resource fault at iteration 3 (healed and verified), a goal-drift
regression at iteration 5 (re-aligned from checkpoint), and pauses at a
human gate at iteration 6.

## Results (seed 7, from the actual run)

- Termination `met_standard` after **7 iterations**; composite 0.217 -> **0.960**
  against a 0.85 standard.
- Fault: 1 injected (resource), **recovered and verified**; lesson retained.
- Goal drift: 1 event (regression 0.108 > 0.10 threshold); re-aligned from
  checkpoint and resumed.
- Checkpoints: 3 taken; human gates: 1 approved; ledger: 22 entries, chain intact.
- Plateau behaviour: with an unsatisfiable requirement capping the score,
  terminates `plateau` after 8 iterations (best 0.800).
- Budget behaviour: with budget 12.0 at 5.0/iteration, terminates
  `budget_exhausted` after 3 iterations.

See `results/results.md` and `results/charts.png`.
