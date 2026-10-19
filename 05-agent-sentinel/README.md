# agent-sentinel — runtime security for governed agents

## Problem

Design-time governance says what an agent **should** do. Nothing watches
what it **actually** does at runtime: tool calls, network destinations,
data movement. The dangerous behaviours are runtime behaviours — a new
egress destination appearing at 2am, a tool invoked outside its scope,
an egress-volume spike, a prompt injected through a tool output, data
walking out the door. Static policies cannot see any of this.

## Solution

agent-sentinel is a phased runtime-security system for governed AI
agents:

- **Phase 0 — runtime security contract.** Derived deterministically
  from the live agent registry via a transparent risk-tiering rubric
  (low / moderate / high / critical). Each contract states approved
  egress (governed back-ends only), allowed tool scopes, a data ceiling,
  per-run action and egress-byte budgets that tighten with risk, whether
  a human gate is required (high / critical), and planted honeytokens.
- **Phase 1 — baselines + detect-only scoring.** Learns each agent's
  normal egress / tool set / volume from a normal telemetry window, then
  scores every event against contract + baseline. Critical findings:
  honeytoken tripwire, self-exfiltration, new egress. High findings:
  out-of-scope tool, volume spike, prompt injection, data-ceiling
  breach, run-budget breach. Each finding maps to MITRE ATLAS and OWASP
  Top 10 for LLM Applications. Action is always `detect_only` — the
  scorer never blocks. Contracts and findings go on a tamper-evident,
  append-only hash chain.
- **Telemetry seam.** Adapters turn signals into events tagged with
  provenance (`live` vs `simulated`). The simulated feed ships with an
  injected rogue sequence for demonstration, excluded from baseline
  learning so it reads as an anomaly.
- **Phase 2 — human-approval gates.** A high-risk action from a
  human-gated agent is HELD until a person approves or denies. Nothing
  auto-executes.
- **Phase 3 — containment.** Trigger: honeytoken tripwires, or a
  per-agent circuit breaker (2 critical findings in a 600 s window).
  Response: model-independent network kill-switch + quarantine.
  Containment is applied **only on human confirmation**, is stored
  persistently, is reported to platform monitoring as a self-healing
  action, and is **releasable** — never silent, never irreversible. Every
  transition opens a tamper-evident incident record.
- **Phase 4 — continuous evaluations.** Seeded stand-in harnesses score
  capability / cheating / scheming / robustness per agent. Alarms:
  capability jump > 15 points, cheating rate > 40%, scheming rate >
  30%. An alarm returns the agent to intake for re-review, closing the
  runtime -> design-time loop.

## Architecture

```
src/governed_agents/agent_sentinel/
  registry.py      live agent registry (explicit; no invented agents)
  contracts.py     risk rubric + deterministic contract derivation
  telemetry.py     events, provenance tags, seeded simulated feed
  baselines.py     per-agent normal-behaviour baselines
  scorer.py        detect-only scoring + ATLAS/OWASP finding catalog
  chain.py         tamper-evident append-only hash chain
  gates.py         human-approval gates (hold / approve / deny)
  containment.py   circuit breaker + human-confirmed, reversible containment
  evals.py         seeded stand-in eval harnesses + alarm thresholds
  monitoring.py    platform monitoring bus (self-healing reports)
```

## How to run

```bash
cd 05-agent-sentinel
python3 demo.py            # full seeded end-to-end run
python3 tests/test_smoke.py   # 20 smoke tests
```

Quickstart: `examples/05_agent_sentinel_demo.py` (runs the same demo).

## Results (seeded run; see `results/results.md`)

- 6 agents registered; tiers: low=1, moderate=3, high=1, critical=1.
- 2,400-event baseline window; 726-event live stream with 6 injected
  rogue events.
- 14 findings (6 critical, 8 high); detection rate **1.00** on all
  8 finding types (honeytoken tripwire x2, self-exfiltration x2,
  new egress x2, volume spike x2, out-of-scope tool, prompt injection,
  data-ceiling breach, run-budget breach x3).
- **0 false positives** on 720 clean live events (0.00 per 1000).
- Gates: 2 held, 1 approved, 1 denied (approver s.chen).
- Circuit breaker tripped for payment-ops; incident INC-0001
  human-confirmed (kill-switch on, quarantined), probe egress blocked,
  then released; state persisted and reloaded consistently.
- Eval alarm: research-agent capability +18.0 (> 15) -> returned to
  intake for re-review.
- Hash chain: 28 entries, verification OK.

## Honest limits

- Telemetry here is **simulated and seeded**; the rogue sequence is
  injected by the demo. A production deployment needs real adapters
  (eBPF / proxy / tool-gateway taps) with `live` provenance.
- The evaluation harnesses are **seeded stand-ins**, not live model
  evaluations; they demonstrate the alarm-and-re-review loop, not
  measurement of any real model.
- ATLAS mappings are best-effort: technique names are used where the
  public MITRE ATLAS taxonomy defines them
  (e.g. "Exfiltration via Cyber Means", "LLM Prompt Injection");
  otherwise the finding maps at the ATLAS tactic level, which the
  finding catalog states explicitly.
- The 0.00 false-positive rate reflects a clean simulated feed; real
  traffic will need threshold tuning (spike sigma, floors) per agent.
- Containment's kill-switch is enforced at this package's adapter
  layer; a real deployment must enforce it in the network fabric.
