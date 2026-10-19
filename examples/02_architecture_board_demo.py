"""Quickstart: brief the architecture board and read its verdict."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.architecture_board import (
    ChiefArchitect, Priorities, Requirement,
)

req = Requirement(
    title="Real-time fraud scoring platform",
    problem="Score payment transactions for fraud before settlement.",
    throughput="10,000 req/s sustained",
    latency_budget="p99 < 100ms",
    data_sensitivity="PII in scope (cardholder data)",
    compliance="PCI DSS",
    budget_posture="cost-aware; latency first",
    deployment_target="cloud",
    availability_target="99.95%",
)
pri = Priorities(cost=2, latency=5, scalability=5, robustness=4,
                 integration=3, simplicity=3)

result = ChiefArchitect(seed=7).run(req, pri)

print("Blueprint:")
for domain in ["software", "cloud", "ai_ml", "data", "agentic"]:
    print(f"  {domain:10s} -> {result.blueprint[domain].name}")
print(f"\nCritic: {result.critic_iterations} iteration(s), "
      f"{len(result.critic_findings)} finding(s) remain, "
      f"{sum(1 for r in result.policy_results if not r.passed)} policy violation(s), "
      f"{len(result.missing_info)} missing field(s).")
print("\nDone. See 02-architecture-board/demo.py for the full review incl. ADR.")
