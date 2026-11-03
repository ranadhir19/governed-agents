"""Quickstart for agent-sentinel (application 5 of the governed-agents repo).

Runs the full seeded end-to-end demo: registry -> contracts -> baselines ->
detect-only scoring with ATLAS/OWASP-mapped findings -> human gates ->
human-confirmed containment -> continuous evals with re-review alarms.

Usage:
    cd <repo root>
    python3 examples/05_agent_sentinel_demo.py
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

DEMO = os.path.join(ROOT, "05-agent-sentinel", "demo.py")


def main() -> None:
    print("agent-sentinel quickstart: running the seeded end-to-end demo...\n")
    runpy.run_path(DEMO, run_name="__main__")
    print("\nquickstart complete: results in 05-agent-sentinel/results/")


if __name__ == "__main__":
    main()
