"""Quickstart: route a short brief to the expert council and print the verdict."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.expert_council import (
    EXPERTS, Expert, classify, parse_material, route, synthesise,
)

BRIEF = """TITLE: Canary releases for a loan-approval model
ABSTRACT: We ship a credit scoring model with canary deployment and rollback.
CLAIMS: Fewer bad deploys.
METHODS: A model registry versions every artefact; model monitoring watches
for drift detection; a single seed pilot ran on 20k applications with a
train test split and a baseline. No incident response plan exists yet.
"""


def main():
    material = parse_material(BRIEF)
    classification = classify(material, EXPERTS)
    by_id = {s["id"]: Expert(s) for s in EXPERTS}
    routed = route(classification, by_id, threshold=0.18, top_k=6)
    print("routed experts:", ", ".join(e.name for e, _, _ in routed))
    opinions = [e.opine(material) for e, _, _ in routed]
    vocab = set(w for s in EXPERTS for c in s["concepts"] for w in c.split())
    verdict = synthesise(material, opinions, vocab)
    for dim, val in verdict["dimensions"].items():
        print("  %-14s %d/10" % (dim, val))
    print("recommendation:", verdict["recommendation"].upper())
    print("OK")


if __name__ == "__main__":
    main()
