"""Diagnostician and reviser.

The diagnostician turns a panel critique into concrete directives aimed at
the weakest dimensions first. The reviser applies them to produce the next
candidate. Both the proposer and the reviser are pluggable hooks
(``prompt -> text`` style callables for real LLM use); deterministic seeded
defaults keep every run reproducible.
"""

import copy
from dataclasses import dataclass, field


@dataclass
class Directive:
    dimension: str      # critic name
    item: str           # checklist item name
    text: str           # concrete instruction for the reviser
    priority: float     # higher = fix first


class Diagnostician:
    """Weakest dimensions first: priority = critic weight * (1 - score)."""

    def diagnose(self, panel_result):
        directives = []
        for critic in panel_result.per_critic.values():
            gap = 1.0 - critic.score
            if gap <= 0:
                continue
            for item in critic.failed_items:
                directives.append(Directive(
                    dimension=critic.critic,
                    item=item,
                    text=f"[{critic.critic}] fix '{item}': {item.replace('_', ' ')}",
                    priority=gap,
                ))
        directives.sort(key=lambda d: d.priority, reverse=True)
        return directives


_OWNERS = ["A. Rivera", "J. Chen", "M. Okafor", "S. Patel"]
_DUES = ["2026-11-15", "2026-11-30", "2026-12-15", "2027-01-15"]

_SECTION_TEXT = {
    "objectives": ("Deliver the analytics pipeline migration on schedule with zero data loss, "
                   "cut query latency by 40 percent, and keep every downstream dashboard green [E1]."),
    "scope": ("In scope: pipeline code, orchestration jobs, and dashboard queries. Out of scope: "
              "warehouse vendor change and historical reprocessing beyond 90 days [E2]."),
    "success_criteria": ("Migration complete by the target date, p95 query latency down 40 percent, "
                         "zero Sev1 incidents in the first 30 days, and sign-off from data consumers [E1]."),
}


def _fix_item(plan, item, rng):
    """Apply one deterministic fix. Returns True if something changed."""
    secs = plan.setdefault("sections", {})
    ms = plan.setdefault("milestones", [])
    risks = plan.setdefault("risks", [])
    changed = False

    if item in ("has_objectives", "has_scope", "has_success_criteria"):
        key = item.replace("has_", "")
        if not secs.get(key, "").strip():
            secs[key] = _SECTION_TEXT[key]
            changed = True
    elif item == "has_title" and not plan.get("title", "").strip():
        plan["title"] = "Analytics pipeline migration plan"
        changed = True
    elif item == "milestones_ge_3":
        need = 3 - len(ms)
        base = ["Kickoff and scope lock", "Migrate staging pipeline", "Cut over production traffic"]
        for i in range(need):
            ms.append({"name": base[(len(ms)) % len(base)], "owner": None, "due": None,
                       "next_action": None, "needs_approval": False, "risky": False})
            changed = True
    elif item == "risks_ge_2":
        need = 2 - len(risks)
        for i in range(need):
            risks.append({"name": f"Identified risk {len(risks)+1}: data skew during cutover",
                          "mitigation": None, "severity": "medium"})
            changed = True
    elif item == "has_budget_total":
        b = plan.setdefault("budget", {})
        if b.get("total") is None:
            bd = b.get("breakdown") or [{"item": "engineering", "amount": 60000.0},
                                        {"item": "contingency", "amount": 15000.0}]
            b["breakdown"] = bd
            b["total"] = sum(x["amount"] for x in bd)
            changed = True
    elif item == "stakeholders_ge_2":
        st = plan.setdefault("stakeholders", [])
        for s in ["Data platform lead", "Analytics consumers"]:
            if s not in st:
                st.append(s); changed = True
    elif item == "assumptions_ge_1":
        asm = plan.setdefault("assumptions", [])
        if not asm:
            asm.append("Source schemas remain stable during migration [E1]")
            changed = True
    elif item == "milestones_have_owners":
        for i, m in enumerate(ms):
            if not m.get("owner"):
                m["owner"] = _OWNERS[i % len(_OWNERS)]; changed = True
    elif item == "milestones_have_dues":
        for i, m in enumerate(ms):
            if not m.get("due"):
                m["due"] = _DUES[i % len(_DUES)]; changed = True
    elif item == "budget_sums":
        b = plan.setdefault("budget", {})
        bd = b.get("breakdown") or []
        if bd:
            b["total"] = sum(x.get("amount", 0) for x in bd); changed = True
    elif item == "risks_have_mitigations":
        for r in risks:
            if not r.get("mitigation"):
                r["mitigation"] = "Add monitoring, runbook entry, and rollback step; lead: A. Rivera"
                changed = True
    elif item == "no_empty_sections":
        for k, v in secs.items():
            if not str(v).strip():
                secs[k] = _SECTION_TEXT.get(k, "Documented and reviewed by the working group [E2].")
                changed = True
    elif item == "evidence_ge_2":
        ev = plan.setdefault("evidence", [])
        while len(ev) < 2:
            ev.append({"source": f"E{len(ev)+1}: staging migration postmortem",
                       "note": "Prior migration completed with zero data loss."})
            changed = True
    elif item == "assumptions_cite_evidence":
        for i, s in enumerate(plan.get("assumptions", [])):
            if "[E" not in s:
                plan["assumptions"][i] = s.rstrip() + " [E1]"; changed = True
    elif item == "budget_amounts_positive":
        b = plan.setdefault("budget", {})
        if (b.get("total") or 0) <= 0:
            b["total"] = 75000.0; changed = True
        for x in b.get("breakdown", []):
            if x.get("amount", 0) <= 0:
                x["amount"] = 10000.0; changed = True
    elif item == "no_placeholders":
        for k, v in secs.items():
            for tok in ("TODO", "TBD", "XXX"):
                if tok in str(v).upper():
                    secs[k] = str(v).replace(tok, "documented")
                    secs[k] = secs[k].replace("Documented", "Documented")
                    changed = True
        # ensure replacement text keeps sections substantive
        for k, v in secs.items():
            if len(str(v)) < 40:
                secs[k] = str(v) + " Reviewed and agreed by the working group [E2]."
                changed = True
    elif item == "sections_min_length":
        for k, v in secs.items():
            if len(str(v)) < 40:
                secs[k] = str(v) + " Reviewed and agreed by the working group [E2]."
                changed = True
    elif item == "title_concise":
        t = plan.get("title", "")
        if not t.strip():
            plan["title"] = "Analytics pipeline migration plan"; changed = True
        elif len(t) > 120:
            plan["title"] = t[:120]; changed = True
    elif item == "risky_flagged":
        for m in ms:
            if m.get("risky") and not m.get("needs_approval"):
                m["needs_approval"] = True; changed = True
    elif item == "no_banned_actions":
        for m in ms:
            name = str(m.get("name", "")).lower()
            for b in ("drop table", "rm -rf", "delete production", "disable backups"):
                if b in name:
                    m["name"] = "Safely decommission legacy job (with approval)"
                    m["needs_approval"] = True; changed = True
    elif item == "high_risks_have_owner":
        for r in risks:
            if r.get("severity") == "high" and "lead" not in str(r.get("mitigation", "")).lower():
                r["mitigation"] = (str(r.get("mitigation", "")) + " lead: A. Rivera").strip()
                changed = True
    elif item == "milestones_have_next_actions":
        for m in ms:
            if not m.get("next_action"):
                m["next_action"] = "Draft, circulate for review, and confirm owner sign-off"
                changed = True
    elif item == "owners_distinct_ge_2":
        owners = {m.get("owner") for m in ms if m.get("owner")}
        i = 0
        while len(owners) < 2 and i < len(ms):
            cand = _OWNERS[(len(owners) + i) % len(_OWNERS)]
            if cand not in owners:
                ms[i]["owner"] = cand; owners.add(cand); changed = True
            i += 1
    elif item == "has_kickoff":
        if not any("kickoff" in str(m.get("name", "")).lower() or "start" in str(m.get("name", "")).lower()
                   for m in ms):
            ms.insert(0, {"name": "Kickoff and scope lock", "owner": _OWNERS[0], "due": _DUES[0],
                          "next_action": "Schedule kickoff and lock scope", "needs_approval": False,
                          "risky": False})
            changed = True
    return changed


class Reviser:
    """Deterministic reviser: applies up to `capability` directives per call."""

    def __init__(self, capability=4):
        self.capability = capability

    def revise(self, plan, directives, rng):
        new_plan = copy.deepcopy(plan)
        applied = 0
        for d in directives:
            if applied >= self.capability:
                break
            if _fix_item(new_plan, d.item, rng):
                applied += 1
        return new_plan, applied


def propose_plan(task, rng, defect_level=1.0):
    """Seeded proposer: emits a plan with a controlled number of defects."""
    plan = {
        "title": "Migration plan draft",
        "sections": {
            "objectives": "",
            "scope": "Move the pipeline. TODO details",
            "success_criteria": "",
        },
        "milestones": [
            {"name": "Kickoff", "owner": None, "due": None, "next_action": None,
             "needs_approval": False, "risky": False},
            {"name": "Migrate production traffic", "owner": None, "due": None,
             "next_action": None, "needs_approval": False, "risky": True},
        ],
        "risks": [
            {"name": "Cutover data skew", "mitigation": None, "severity": "high"},
        ],
        "budget": {"total": None, "breakdown": []},
        "stakeholders": ["Data platform lead"],
        "assumptions": ["Schemas stay stable"],
        "evidence": [],
    }
    # defect_level scales how sparse the draft is; 1.0 = maximally sparse draft
    if defect_level < 0.5:
        plan["sections"]["objectives"] = _SECTION_TEXT["objectives"]
        plan["evidence"] = [{"source": "E1: staging migration postmortem", "note": "ok"}]
    return plan
