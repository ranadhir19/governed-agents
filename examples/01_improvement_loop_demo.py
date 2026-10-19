"""Quickstart: autonomous critic-gated improvement loop.

Runs a small seeded loop (no fault injection): propose -> critique ->
diagnose -> revise -> repeat until the quality standard is met.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.improvement_loop import ImprovementEngine, LoopConfig


def main():
    cfg = LoopConfig(
        task="Draft a project plan for migrating the analytics pipeline",
        quality_threshold=0.85,
        max_iterations=10,
        budget=50.0,
        cost_per_iteration=5.0,
        seed=7,
    )
    report = ImprovementEngine(cfg).run()
    print("termination :", report.termination)
    print("iterations  :", report.iterations_run)
    print("best score  : %.3f" % report.best_score)
    print("trajectory  :", " ".join("%.2f" % s for s in report.score_history))
    print("ledger      : %d entries, intact=%s"
          % (report.ledger_entries, report.ledger_ok))
    assert report.termination == "met_standard", report.termination
    print("quickstart OK")


if __name__ == "__main__":
    main()
