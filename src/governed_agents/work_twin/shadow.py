"""Shadow mode: uncontaminated labels at no risk.

The twin commits a prediction; the human decides independently WITHOUT seeing
it. The seal is enforced in code:

  * ``commit`` seals a prediction for a case;
  * ``record_human_decision`` refuses unless a sealed, unrevealed prediction
    exists -- the human cannot have seen what was never revealed;
  * ``reveal`` refuses until the human decision is recorded.

Temporal holdout: fit on earlier cases (by time), score on later ones, so the
twin is evaluated on cases it never trained on.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SealedPrediction:
    case_id: str
    prediction: int
    confidence: float
    revealed: bool = False
    human_decision: Optional[int] = None


class ShadowLog:
    def __init__(self) -> None:
        self._sealed: Dict[str, SealedPrediction] = {}

    def commit(self, case_id: str, prediction: int, confidence: float) -> None:
        if case_id in self._sealed:
            raise ValueError("prediction already committed for %s" % case_id)
        if prediction not in (0, 1):
            raise ValueError("prediction must be 0/1")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        self._sealed[case_id] = SealedPrediction(case_id, prediction, confidence)

    def record_human_decision(self, case_id: str, decision: int) -> None:
        """The human decides without seeing the prediction -- enforced: a
        decision can only be recorded against a sealed, unrevealed prediction."""
        sp = self._sealed.get(case_id)
        if sp is None:
            raise KeyError("no sealed prediction for %s: commit first" % case_id)
        if sp.revealed:
            raise PermissionError(
                "label contaminated: prediction for %s was revealed before "
                "the human decided; this label is unusable" % case_id)
        if sp.human_decision is not None:
            raise ValueError("human decision already recorded for %s" % case_id)
        if decision not in (0, 1):
            raise ValueError("decision must be 0/1")
        sp.human_decision = decision

    def reveal(self, case_id: str) -> Tuple[int, int]:
        """Reveal only after the human decision is on record."""
        sp = self._sealed[case_id]
        if sp.human_decision is None:
            raise PermissionError(
                "reveal refused: no human decision recorded for %s" % case_id)
        sp.revealed = True
        return sp.prediction, sp.human_decision

    def decided_cases(self) -> List[SealedPrediction]:
        return [sp for sp in self._sealed.values() if sp.human_decision is not None]

    def agreement(self) -> Optional[float]:
        decided = self.decided_cases()
        if not decided:
            return None
        return float(np.mean([sp.prediction == sp.human_decision for sp in decided]))

    def expected_calibration_error(self, n_bins: int = 10) -> Optional[float]:
        """ECE of twin confidence against human agreement."""
        decided = self.decided_cases()
        if not decided:
            return None
        conf = np.array([sp.confidence for sp in decided])
        agree = np.array([float(sp.prediction == sp.human_decision) for sp in decided])
        ece = 0.0
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        for b in range(n_bins):
            lo, hi = edges[b], edges[b + 1]
            mask = (conf > lo) & (conf <= hi) if b > 0 else (conf >= lo) & (conf <= hi)
            if mask.sum() == 0:
                continue
            ece += (mask.sum() / len(conf)) * abs(conf[mask].mean() - agree[mask].mean())
        return float(ece)

    def calibration_curve(self, n_bins: int = 10) -> List[Dict[str, float]]:
        decided = self.decided_cases()
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        conf = np.array([sp.confidence for sp in decided])
        agree = np.array([float(sp.prediction == sp.human_decision) for sp in decided])
        curve = []
        for b in range(n_bins):
            lo, hi = edges[b], edges[b + 1]
            mask = (conf > lo) & (conf <= hi) if b > 0 else (conf >= lo) & (conf <= hi)
            if mask.sum() == 0:
                continue
            curve.append({"bin_center": float((lo + hi) / 2),
                          "mean_confidence": float(conf[mask].mean()),
                          "observed_agreement": float(agree[mask].mean()),
                          "n": int(mask.sum())})
        return curve


def temporal_holdout(
    cases: List[Dict[str, Any]],
    fit: Callable[[List[Dict[str, Any]], Dict[str, Any]], int],
    task_type: str,
    train_frac: float = 0.7,
) -> Dict[str, Any]:
    """Fit the twin's rule on earlier cases, score it on later ones.

    ``fit(train_cases, case) -> prediction``. Confidence here is fixed at
    0.85 on the holdout slice, keeping the evaluation honest.
    """
    members = sorted([c for c in cases if c.get("task_type") == task_type],
                     key=lambda c: c["created_time"])
    if len(members) < 4:
        raise ValueError("need at least 4 cases for a temporal holdout")
    cut = max(2, int(len(members) * train_frac))
    train, test = members[:cut], members[cut:]
    log = ShadowLog()
    for c in test:
        pred = fit(train, c)
        log.commit(c["case_id"], int(pred), 0.85)
        log.record_human_decision(c["case_id"], int(c["outcome"]))
    return {"n_train": len(train), "n_test": len(test),
            "agreement": log.agreement(), "ece": log.expected_calibration_error(),
            "log": log}
