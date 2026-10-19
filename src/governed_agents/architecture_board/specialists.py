"""Domain specialists: each owns a pattern catalogue and scores it.

Scoring: fit = weighted mean of the six dimension scores, weights from the
requester's 1-5 priorities, plus tiny seeded Gaussian jitter (sd 0.03) as a
deterministic tiebreaker. numpy only.
"""

import numpy as np

from .models import DIMENSIONS, DOMAIN_LABELS, Pattern, Priorities, Requirement, ScoredPattern
from .patterns import CATALOGUES


class Specialist:
    """One domain specialist on the board."""

    def __init__(self, domain: str):
        self.domain = domain
        self.label = DOMAIN_LABELS[domain]
        self.catalogue = CATALOGUES[domain]

    def score(self, requirement: Requirement, priorities: Priorities,
              rng: np.random.Generator) -> list:
        """Score every pattern in the catalogue; return ranked ScoredPatterns."""
        w = np.array([priorities.weights()[d] for d in DIMENSIONS], dtype=float)
        w = w / w.sum()
        ranked = []
        for pat in self.catalogue:
            s = np.array([pat.scores[d] for d in DIMENSIONS], dtype=float)
            fit = float(np.dot(s, w) + rng.normal(0.0, 0.03))
            parts = {d: float(s[i] * w[i]) for i, d in enumerate(DIMENSIONS)}
            ranked.append(ScoredPattern(pattern=pat, fit=fit, weighted_parts=parts))
        ranked.sort(key=lambda sp: sp.fit, reverse=True)
        return ranked

    def brief(self, requirement: Requirement) -> str:
        """The sub-brief this specialist received from the chief architect."""
        return (
            f"{self.label} specialist: evaluate '{requirement.title}' for the "
            f"{self.label.lower()} layer. Problem: {requirement.problem}"
        )


def all_specialists() -> list:
    return [Specialist(d) for d in ["software", "cloud", "ai_ml", "data", "agentic"]]
