"""Cohort analysis over TASK TYPES, never people.

The one-way boundary from the person plane to the cohort plane is structural:
no function in this module accepts a person, manager, team, or any individual
identifier and returns their figures. The safest guarantee is that the code to
do it does not exist -- see ``test_no_person_level_function``.

Suppression (two rules, applied to every cell):
  1. minimum cohort: a cell with fewer than 5 cases is suppressed;
  2. maximum single-contributor share: a cell where one contributor accounts
     for more than 50% of cases is suppressed.
A suppressed cell returns ("suppressed", reason) -- never a blank, never a
zero, which would read as a finding.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

MIN_COHORT = 5
MAX_SINGLE_SHARE = 0.50


@dataclass
class Cell:
    band: str
    n: int
    outcome_rate: Optional[float]
    status: str  # "ok" or "suppressed"
    reason: Optional[str] = None

    def display(self) -> str:
        if self.status == "suppressed":
            return "suppressed (%s)" % self.reason
        return "n=%d, outcome_rate=%.3f" % (self.n, self.outcome_rate)


def _contributor_shares(cases: List[Dict[str, Any]]) -> Dict[Any, float]:
    counts: Dict[Any, int] = {}
    for c in cases:
        key = c.get("contributor_ref")
        counts[key] = counts.get(key, 0) + 1
    n = len(cases)
    return {k: v / n for k, v in counts.items()}


def cohort_table(
    cases: List[Dict[str, Any]],
    task_type: str,
    band_of: Callable[[Dict[str, Any]], str],
    outcome_of: Callable[[Dict[str, Any]], int] = lambda c: int(c["outcome"]),
) -> List[Cell]:
    """Aggregate cases of one TASK TYPE into cohort cells.

    ``cases`` are plain case dicts; ``band_of`` maps a case to a cohort band
    (e.g. an amount band). There is no parameter for selecting an individual.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in cases:
        if c.get("task_type") != task_type:
            continue
        band = band_of(c)
        groups.setdefault(band, []).append(c)

    cells: List[Cell] = []
    for band in sorted(groups):
        members = groups[band]
        n = len(members)
        if n < MIN_COHORT:
            cells.append(Cell(band, n, None, "suppressed",
                              "cohort size %d below minimum %d" % (n, MIN_COHORT)))
            continue
        shares = _contributor_shares(members)
        top_share = max(shares.values()) if shares else 0.0
        if top_share > MAX_SINGLE_SHARE:
            cells.append(Cell(band, n, None, "suppressed",
                              "single-contributor share %.0f%% exceeds 50%% maximum"
                              % (100.0 * top_share)))
            continue
        rate = sum(outcome_of(c) for c in members) / n
        cells.append(Cell(band, n, rate, "ok"))
    return cells


def task_type_summary(
    cases: List[Dict[str, Any]],
    task_type: str,
    outcome_of: Callable[[Dict[str, Any]], int] = lambda c: int(c["outcome"]),
) -> Dict[str, Any]:
    """Whole-task-type aggregate. Still no individual selection."""
    members = [c for c in cases if c.get("task_type") == task_type]
    n = len(members)
    if n < MIN_COHORT:
        return {"task_type": task_type, "status": "suppressed",
                "reason": "cohort size %d below minimum %d" % (n, MIN_COHORT)}
    shares = _contributor_shares(members)
    top_share = max(shares.values()) if shares else 0.0
    if top_share > MAX_SINGLE_SHARE:
        return {"task_type": task_type, "status": "suppressed",
                "reason": "single-contributor share %.0f%% exceeds 50%% maximum"
                         % (100.0 * top_share)}
    return {"task_type": task_type, "status": "ok", "n": n,
            "outcome_rate": sum(outcome_of(c) for c in members) / n}
