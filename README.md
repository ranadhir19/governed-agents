# Governed Agents

Six general-purpose, open implementations of governed agent operations — the concepts behind
running autonomous agents safely in production: improve them, advise on their architecture,
consult experts, twin workers without surveillance, watch them at runtime, and govern their
delivery.

Each application is a complete, runnable system: a Python library (`src/governed_agents/`),
a demo with measured results, and a passing test suite. Everything is deterministic and
seeded — re-running reproduces every number. Standard library plus numpy/scipy/matplotlib only.

| # | Application | What it does | Headline result |
|---|-------------|--------------|-----------------|
| 01 | [improvement-loop](01-improvement-loop/) | Autonomous critic-gated improvement loop for long-running agents: propose → critique → diagnose → revise, with self-healing, safe checkpoints and explicit termination | 0.217 → 0.960 in 7 iterations; fault recovered, drift re-aligned |
| 02 | [architecture-board](02-architecture-board/) | Multi-agent architecture advisory board: 5 specialists, 44-pattern catalogue, design critic, policy compliance, ADR output | Critic caught a retrieval-only pick for a scoring task; optimiser fixed it |
| 03 | [expert-council](03-expert-council/) | Orchestrated 8-expert reference system: merit verdicts on 6 dimensions, continuous cultivation, knowledge-graph Q&A | Routing F1 0.810; all experts Practitioner → Senior in 3 cycles |
| 04 | [work-twin](04-work-twin/) | Principal-split worker twin: discretion measured not asserted, shadow mode, L0–L5 autonomy ladder | Planted discretion recovered; both leakage traps caught; 0.963 shadow agreement |
| 05 | [agent-sentinel](05-agent-sentinel/) | Runtime security for agents: contracts, detect-only scoring, human gates, reversible containment, continuous evals | 1.00 detection on 8 finding types; 0 FP on 720 clean events |
| 06 | [design-registry](06-design-registry/) | Design-to-delivery governance registry: one record per project, strict validation, completeness, reachability probes | Bad saves refused with actionable messages; corrupt store degrades gracefully |

## Quick start

```bash
pip install -e .
PYTHONPATH=src python3 examples/01_improvement_loop_demo.py
```

Each application also runs standalone from its own directory — see its README.

## Design principles

- **General, not branded.** These are open implementations of widely-applicable concepts.
- **Measured, not asserted.** Every claim carries a seeded experiment behind it.
- **Deterministic.** Same seed, same numbers, on any machine.
- **Honest limits.** Each README documents what its simulations do not prove.

## License

MIT — see [LICENSE](LICENSE).
