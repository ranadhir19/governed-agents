"""agent_sentinel: runtime security for governed AI agents.

Design-time governance says what an agent SHOULD do. This package watches
what it ACTUALLY does at runtime: tool calls, network destinations, data
movement. Dangerous behaviours are runtime behaviours; this package
detects them and contains the high-risk ones.

Phases:
  0 - runtime security contract per agent, derived deterministically from
      the live agent registry via a transparent risk-tiering rubric.
  1 - baselines and detect-only scoring against contract + baseline.
      Contracts and findings are recorded on a tamper-evident hash chain.
  2 - human-approval gates: high-risk actions from gated agents are HELD.
  3 - containment: circuit breaker + human-confirmed, reversible
      network kill-switch and quarantine. Never silent, never irreversible.
  4 - continuous evaluations: capability / cheating / scheming /
      robustness stand-ins with alarm thresholds; alarms send the agent
      back to intake for re-review.

All randomness is seeded. Evaluation harnesses are seeded stand-ins and
are documented as such.
"""

from governed_agents.agent_sentinel.registry import Agent, AgentRegistry
from governed_agents.agent_sentinel.contracts import (
    SecurityContract,
    derive_contract,
    derive_all,
    risk_tier,
    RUBRIC,
)
from governed_agents.agent_sentinel.telemetry import Event, Provenance, SimulatedFeed
from governed_agents.agent_sentinel.baselines import Baseline, learn_baselines
from governed_agents.agent_sentinel.scorer import Finding, Scorer, FINDING_CATALOG
from governed_agents.agent_sentinel.chain import HashChain
from governed_agents.agent_sentinel.gates import GateQueue, GateDecision, is_high_risk
from governed_agents.agent_sentinel.containment import (
    CircuitBreaker,
    ContainmentController,
    ContainmentState,
)
from governed_agents.agent_sentinel.evals import EvalSuite, EvalResult, EvalAlarm
from governed_agents.agent_sentinel.monitoring import MonitoringBus

__all__ = [
    "Agent",
    "AgentRegistry",
    "SecurityContract",
    "derive_contract",
    "derive_all",
    "risk_tier",
    "RUBRIC",
    "Event",
    "Provenance",
    "SimulatedFeed",
    "Baseline",
    "learn_baselines",
    "Finding",
    "Scorer",
    "FINDING_CATALOG",
    "HashChain",
    "GateQueue",
    "GateDecision",
    "is_high_risk",
    "CircuitBreaker",
    "ContainmentController",
    "ContainmentState",
    "EvalSuite",
    "EvalResult",
    "EvalAlarm",
    "MonitoringBus",
]
