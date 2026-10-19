"""Critic panel: deterministic, explainable quality gates.

Each critic owns a checklist of named requirement items. A critic scores a
candidate artifact as the fraction of checklist items it satisfies and
passes when the score meets its own threshold. The panel combines critics
into one weighted composite score. Domain critics are pluggable via
``CriticPanel.register``.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Artifact schema (a synthetic project plan; any dict following it works)
# ---------------------------------------------------------------------------
# {
#   "title": str,
#   "sections": {"objectives": str, "scope": str, "success_criteria": str},
#   "milestones": [{"name","owner","due","next_action","needs_approval","risky"}],
#   "risks": [{"name","mitigation","severity"}],
#   "budget": {"total": float|None, "breakdown": [{"item","amount"}]},
#   "stakeholders": [str],
#   "assumptions": [str],          # grounded ones cite evidence as "[E1]"
#   "evidence": [{"source","note"}],
# }


@dataclass
class ChecklistItem:
    name: str
    description: str
    check: callable  # artifact -> bool


@dataclass
class CriticResult:
    critic: str
    score: float
    passed_items: list
    failed_items: list
    total: int
    passed: bool


@dataclass
class PanelResult:
    composite: float
    per_critic: dict  # name -> CriticResult
    total_items: int
    passed_items: int


class Critic:
    def __init__(self, name, weight, threshold, items):
        self.name = name
        self.weight = weight
        self.threshold = threshold
        self.items = items

    def evaluate(self, artifact):
        passed, failed = [], []
        for item in self.items:
            try:
                ok = bool(item.check(artifact))
            except Exception:
                ok = False
            (passed if ok else failed).append(item.name)
        total = len(self.items)
        score = len(passed) / total if total else 1.0
        return CriticResult(
            critic=self.name,
            score=score,
            passed_items=passed,
            failed_items=failed,
            total=total,
            passed=score >= self.threshold,
        )


class CriticPanel:
    def __init__(self, critics):
        self.critics = list(critics)

    def register(self, critic):
        """Plug in a domain-specific critic."""
        self.critics.append(critic)

    def evaluate(self, artifact):
        per, total_items, passed_items = {}, 0, 0
        for c in self.critics:
            r = c.evaluate(artifact)
            per[c.name] = r
            total_items += r.total
            passed_items += len(r.passed_items)
        weights = sum(c.weight for c in self.critics) or 1.0
        composite = sum(c.weight * per[c.name].score for c in self.critics) / weights
        return PanelResult(
            composite=composite,
            per_critic=per,
            total_items=total_items,
            passed_items=passed_items,
        )


# ---------------------------------------------------------------------------
# Generic critics
# ---------------------------------------------------------------------------

def _sections(a):
    return a.get("sections", {})

def _milestones(a):
    return a.get("milestones", [])

def _risks(a):
    return a.get("risks", [])

def _budget(a):
    return a.get("budget", {}) or {}


def completeness_critic():
    items = [
        ChecklistItem("has_title", "plan has a non-empty title",
                      lambda a: bool(a.get("title", "").strip())),
        ChecklistItem("has_objectives", "objectives section present",
                      lambda a: bool(_sections(a).get("objectives", "").strip())),
        ChecklistItem("has_scope", "scope section present",
                      lambda a: bool(_sections(a).get("scope", "").strip())),
        ChecklistItem("has_success_criteria", "success criteria present",
                      lambda a: bool(_sections(a).get("success_criteria", "").strip())),
        ChecklistItem("milestones_ge_3", "at least 3 milestones",
                      lambda a: len(_milestones(a)) >= 3),
        ChecklistItem("risks_ge_2", "at least 2 risks identified",
                      lambda a: len(_risks(a)) >= 2),
        ChecklistItem("has_budget_total", "budget total stated",
                      lambda a: _budget(a).get("total") is not None),
        ChecklistItem("stakeholders_ge_2", "at least 2 stakeholders",
                      lambda a: len(a.get("stakeholders", [])) >= 2),
        ChecklistItem("assumptions_ge_1", "at least 1 assumption recorded",
                      lambda a: len(a.get("assumptions", [])) >= 1),
    ]
    return Critic("completeness", weight=0.25, threshold=0.80, items=items)


def rigour_critic():
    items = [
        ChecklistItem("milestones_have_owners", "every milestone has an owner",
                      lambda a: all(m.get("owner") for m in _milestones(a)) and len(_milestones(a)) > 0),
        ChecklistItem("milestones_have_dues", "every milestone has a due date",
                      lambda a: all(m.get("due") for m in _milestones(a)) and len(_milestones(a)) > 0),
        ChecklistItem("budget_sums", "breakdown sums to total (within 1%)",
                      lambda a: _budget_sums_ok(a)),
        ChecklistItem("risks_have_mitigations", "every risk has a mitigation",
                      lambda a: all(r.get("mitigation") for r in _risks(a)) and len(_risks(a)) > 0),
        ChecklistItem("no_empty_sections", "no section is blank",
                      lambda a: all(str(v).strip() for v in _sections(a).values()) and len(_sections(a)) > 0),
    ]
    return Critic("rigour", weight=0.20, threshold=0.70, items=items)


def _budget_sums_ok(a):
    b = _budget(a)
    total, bd = b.get("total"), b.get("breakdown", [])
    if total is None or not bd:
        return False
    s = sum(x.get("amount", 0) for x in bd)
    return abs(s - total) <= 0.01 * abs(total) + 1e-9


def grounding_critic():
    items = [
        ChecklistItem("evidence_ge_2", "at least 2 evidence items",
                      lambda a: len(a.get("evidence", [])) >= 2),
        ChecklistItem("assumptions_cite_evidence", "every assumption cites evidence ([E#])",
                      lambda a: len(a.get("assumptions", [])) > 0 and all("[E" in s for s in a["assumptions"])),
        ChecklistItem("budget_amounts_positive", "budget amounts are positive",
                      lambda a: (_budget(a).get("total") or 0) > 0 and all(
                          x.get("amount", 0) > 0 for x in _budget(a).get("breakdown", []))),
    ]
    return Critic("grounding", weight=0.15, threshold=0.60, items=items)


def clarity_critic():
    items = [
        ChecklistItem("no_placeholders", "no TODO/TBD/XXX placeholder tokens",
                      lambda a: not _has_placeholder(a)),
        ChecklistItem("sections_min_length", "every section at least 40 chars",
                      lambda a: all(len(str(v)) >= 40 for v in _sections(a).values()) and len(_sections(a)) > 0),
        ChecklistItem("title_concise", "title under 120 chars",
                      lambda a: 0 < len(a.get("title", "")) <= 120),
    ]
    return Critic("clarity", weight=0.15, threshold=0.70, items=items)


def _has_placeholder(a):
    texts = [a.get("title", "")]
    texts += [str(v) for v in _sections(a).values()]
    texts += [str(m.get("name", "")) for m in _milestones(a)]
    blob = " ".join(texts).upper()
    return any(tok in blob for tok in ("TODO", "TBD", "XXX"))


_BANNED = ("drop table", "rm -rf", "delete production", "disable backups")


def safety_critic():
    items = [
        ChecklistItem("risky_flagged", "risky milestones require approval",
                      lambda a: all((not m.get("risky")) or m.get("needs_approval") for m in _milestones(a))),
        ChecklistItem("no_banned_actions", "no destructive actions planned",
                      lambda a: not any(b in " ".join(
                          str(m.get("name", "")) for m in _milestones(a)).lower() for b in _BANNED)),
        ChecklistItem("high_risks_have_owner", "high-severity risks name a mitigation owner",
                      lambda a: all((r.get("severity") != "high") or ("owner" in str(r.get("mitigation", "")).lower() or "lead" in str(r.get("mitigation", "")).lower())
                                    for r in _risks(a))),
    ]
    return Critic("safety", weight=0.15, threshold=1.00, items=items)


def actionability_critic():
    items = [
        ChecklistItem("milestones_have_next_actions", "every milestone has a next action",
                      lambda a: all(m.get("next_action") for m in _milestones(a)) and len(_milestones(a)) > 0),
        ChecklistItem("owners_distinct_ge_2", "at least 2 distinct owners",
                      lambda a: len({m.get("owner") for m in _milestones(a) if m.get("owner")}) >= 2),
        ChecklistItem("has_kickoff", "a kickoff/start milestone exists",
                      lambda a: any("kickoff" in str(m.get("name", "")).lower() or "start" in str(m.get("name", "")).lower()
                                    for m in _milestones(a))),
    ]
    return Critic("actionability", weight=0.10, threshold=0.70, items=items)


def build_default_panel():
    return CriticPanel([
        completeness_critic(),
        rigour_critic(),
        grounding_critic(),
        clarity_critic(),
        safety_critic(),
        actionability_critic(),
    ])
