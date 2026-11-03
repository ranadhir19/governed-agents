"""End-to-end demo: the architecture board reviews a real-time fraud scoring platform.

Seeded. Prints ranked patterns per layer, critic findings, the
missing-information checklist, and the full Architecture Decision Record.
Also runs the two results experiments (priority sensitivity, critic counts).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import numpy as np

from governed_agents.architecture_board import (
    ChiefArchitect, PolicyChecker, Priorities, Requirement, load_policy,
    parse_document,
)
from governed_agents.architecture_board.models import DOMAIN_LABELS

SEED = 7
HERE = os.path.dirname(os.path.abspath(__file__))


def fraud_requirement() -> Requirement:
    # NOTE: team_size is deliberately omitted to demonstrate the
    # missing-information checklist (the board never infers it).
    return Requirement(
        title="Real-time fraud scoring platform",
        problem=("Score every payment transaction for fraud in real time and "
                 "decline or step-up suspicious ones before settlement."),
        throughput="10,000 req/s sustained, 25,000 req/s peak",
        latency_budget="p99 < 100ms end to end",
        data_sensitivity="PII in scope (cardholder data)",
        compliance="PCI DSS",
        budget_posture="cost-aware; latency and correctness outrank cost",
        deployment_target="cloud",
        availability_target="99.95%",
    )


def fraud_priorities() -> Priorities:
    return Priorities(cost=2, latency=5, scalability=5, robustness=4,
                      integration=3, simplicity=3)


def run_demo() -> None:
    policy_path = os.path.join(HERE, "policy.json")
    checker = PolicyChecker(load_policy(policy_path))
    chief = ChiefArchitect(seed=SEED, policy_checker=checker)

    req = fraud_requirement()
    pri = fraud_priorities()
    result = chief.run(req, pri)

    print("=" * 72)
    print("ARCHITECTURE BOARD REVIEW:", req.title)
    print("=" * 72)
    print("\nPriorities (1-5): " +
          ", ".join(f"{d}={getattr(pri, d)}" for d in
                     ["cost", "latency", "scalability", "robustness",
                      "integration", "simplicity"]))

    print("\n--- Ranked patterns per layer (top 3) ---")
    for domain in ["software", "cloud", "ai_ml", "data", "agentic"]:
        print(f"\n{DOMAIN_LABELS[domain]}:")
        for sp in result.ranked[domain][:3]:
            mark = " <-- chosen" if sp.pattern.name == result.blueprint[domain].name else ""
            print(f"  {sp.fit:5.2f}  {sp.pattern.name}{mark}")

    print("\n--- Critic findings (after optimiser) ---")
    print(f"Critic iterations: {result.critic_iterations}; "
          f"blueprint revisions: {len(result.blueprint_history) - 1}")
    for f in result.critic_findings:
        print(f"  [{f.severity.upper()}] ({f.category}) {f.message}")
        print(f"    -> {f.suggestion}")
    if not result.critic_findings:
        print("  none")

    print("\n--- Policy compliance ---")
    for pr in result.policy_results:
        status = "PASS" if pr.passed else "VIOLATION"
        print(f"  [{status}] {pr.rule_name}")

    print("\n--- Missing-information checklist ---")
    for m in result.missing_info:
        print(f"  [ ] {m}")
    if not result.missing_info:
        print("  none")

    print("\n--- Document parsing demo ---")
    doc = ("We need a real-time fraud scoring platform handling 10,000 req/s with "
           "p99 under 100ms. Cardholder PII is in scope and we must meet PCI DSS. "
           "The system will run in the cloud with 99.95% availability.")
    parsed, notes = parse_document(doc)
    print("Extracted:")
    for n in notes:
        print(f"  {n}")
    print("Still missing (checklist):")
    for m in __import__("governed_agents.architecture_board.inputs",
                        fromlist=["check_missing"]).check_missing(parsed):
        print(f"  [ ] {m.split(':')[0]}")

    print("\n--- Workflow log ---")
    for line in result.workflow_log:
        print(f"  {line}")

    print("\n" + "=" * 72)
    print("ARCHITECTURE DECISION RECORD")
    print("=" * 72)
    print(result.adr_markdown)

    with open(os.path.join(HERE, "results", "demo_result.json"), "w") as fh:
        json.dump({
            "blueprint": {d: p.name for d, p in result.blueprint.items()},
            "top_fits": {d: round(result.ranked[d][0].fit, 3)
                         for d in result.ranked},
            "critic_iterations": result.critic_iterations,
            "findings": [(f.severity, f.category) for f in result.critic_findings],
            "policy": [(r.rule_id, r.passed) for r in result.policy_results],
            "missing_info": [m.split(":")[0] for m in result.missing_info],
        }, fh, indent=2)
    print("\n[demo] wrote results/demo_result.json")


def run_experiments() -> None:
    """Experiment 1: priority-weighting sensitivity.
    Experiment 2: critic finding counts across three briefs."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    checker = PolicyChecker(load_policy(os.path.join(HERE, "policy.json")))
    domains = ["software", "cloud", "ai_ml", "data", "agentic"]

    # -- Experiment 1: sweep the cost priority 1..5, others fixed
    base = fraud_priorities()
    sweep = {}
    for c in range(1, 6):
        pri = Priorities(cost=c, latency=base.latency, scalability=base.scalability,
                         robustness=base.robustness, integration=base.integration,
                         simplicity=base.simplicity)
        chief = ChiefArchitect(seed=SEED, policy_checker=checker)
        res = chief.run(fraud_requirement(), pri)
        sweep[c] = {d: round(res.ranked[d][0].fit, 3) for d in domains}
    with open(os.path.join(HERE, "results", "sensitivity.json"), "w") as fh:
        json.dump(sweep, fh, indent=2)

    # -- Experiment 2: critic counts on three briefs
    briefs = {
        "fraud (real-time, PII)": (
            fraud_requirement(),
            Priorities(cost=2, latency=5, scalability=5, robustness=4,
                       integration=3, simplicity=3)),
        "global trading (ultra-low-latency)": (
            Requirement(
                title="Global trading platform",
                problem=("Match and execute trades globally with microsecond-grade "
                         "ambitions; predict short-term price moves to route orders."),
                throughput="50,000 req/s sustained",
                latency_budget="p99 < 10ms",
                data_sensitivity="internal only",
                compliance="SOC 2",
                team_size="30 engineers",
                budget_posture="cost is no object; speed and uptime dominate",
                deployment_target="cloud",
                availability_target="99.99%"),
            Priorities(cost=1, latency=5, scalability=5, robustness=5,
                       integration=3, simplicity=1)),
        "support copilot (generative, PII)": (
            Requirement(
                title="Customer support copilot",
                problem="Answer customer questions from the help-centre corpus with citations.",
                throughput="50 req/s",
                latency_budget="p99 < 3s",
                data_sensitivity="PII in scope (account data)",
                compliance="SOC 2",
                team_size="8 engineers",
                budget_posture="moderate",
                deployment_target="cloud",
                availability_target="99.9%"),
            Priorities(cost=3, latency=3, scalability=4, robustness=5,
                       integration=4, simplicity=4)),
    }
    counts = {}
    for name, (req, pri) in briefs.items():
        chief = ChiefArchitect(seed=SEED, policy_checker=checker)
        res = chief.run(req, pri)
        # count first-pass findings (what the critic caught before optimisation)
        sev = {"high": 0, "medium": 0, "low": 0}
        for f in res.initial_findings:
            sev[f.severity] += 1
        counts[name] = {"critic_first_pass": sev,
                        "critic_remaining": len(res.critic_findings),
                        "policy_violations": sum(1 for r in res.policy_results if not r.passed),
                        "iterations": res.critic_iterations}
    with open(os.path.join(HERE, "results", "critic_counts.json"), "w") as fh:
        json.dump(counts, fh, indent=2)

    # -- charts
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    xs = sorted(sweep)
    for d in domains:
        ax.plot(xs, [sweep[c][d] for c in xs], marker="o", label=DOMAIN_LABELS[d])
    ax.set_xlabel("cost priority (1-5; other priorities fixed)")
    ax.set_ylabel("fit of top-ranked pattern")
    ax.set_title("Priority-weighting sensitivity")
    ax.set_xticks(xs)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1]
    labels = list(counts)
    x = np.arange(len(labels))
    w = 0.18
    for i, sev in enumerate(["high", "medium", "low"]):
        ax.bar(x + (i - 1.5) * w, [counts[l]["critic_first_pass"][sev] for l in labels],
               width=w, label=f"critic {sev} (first pass)")
    ax.bar(x + 1.5 * w, [counts[l]["policy_violations"] for l in labels],
           width=w, label="policy violations")
    ax.set_xticks(x)
    ax.set_xticklabels([l.split(" (")[0] for l in labels], fontsize=8)
    ax.set_ylabel("count")
    ax.set_title("Critic findings (first pass) and policy violations by brief")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis="y")

    fig.suptitle("Architecture board - seeded experiments (seed=7)", fontsize=11)
    fig.tight_layout()
    out = os.path.join(HERE, "results", "charts.png")
    fig.savefig(out, dpi=110)
    print(f"[experiments] wrote results/charts.png, sensitivity.json, critic_counts.json")


if __name__ == "__main__":
    run_demo()
    run_experiments()
