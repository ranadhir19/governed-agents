"""Synthesise a merit verdict from expert opinions.

Six dimensions, each 0-10: Novelty, Rigour, Feasibility, Impact,
Governance-fit, Risk. Recommendation: accept / revise / reject.
"""

SEVERITY_W = {"critical": 4, "high": 3, "medium": 2, "low": 1}

NOVELTY_CUES = ["novel", "first", "new", "innovative", "breakthrough", "sota",
                "state of the art", "outperform", "improvement", "%"]
FEAS_CUES = ["dataset", "compute", "gpu", "timeline", "milestone", "prototype",
             "pilot", "budget", "infrastructure"]
IMPACT_CUES = ["outperform", "reduction", "savings", "accuracy", "users",
               "customers", "revenue", "lives", "first", "breakthrough"]


def _cue_rate(text, cues):
    low = text.lower()
    return sum(1 for c in cues if c in low) / len(cues)


def _lens_score(opinions):
    vals = {"addressed": 1.0, "partial": 0.5, "unaddressed": 0.0}
    scores = [vals[l["verdict"]] for o in opinions for l in o["lenses"]]
    return sum(scores) / max(1, len(scores))


def synthesise(material, opinions, kb_token_vocab):
    claims = (material.get("claims") or "").lower()
    claim_tokens = set(claims.split())
    overlap = len(claim_tokens & kb_token_vocab) / max(1, len(claim_tokens))
    novelty = min(9, max(2, round(10 * (1 - overlap))))

    rigour = round(10 * _lens_score(opinions))

    feas = 3 + round(7 * min(1.0, _cue_rate(material["text"], FEAS_CUES) * 2.2))
    feas = min(10, feas)

    impact = 2 + round(8 * min(1.0, _cue_rate(material["text"], IMPACT_CUES) * 2.0))
    impact = min(10, impact)

    gov_ops = [o for o in opinions if o["expert_id"] == "gov"]
    if gov_ops:
        gov_score = _lens_score(gov_ops)
        gov_fit = round(10 * gov_score)
    else:
        gov_fit = 5

    risk_load = sum(SEVERITY_W.get(r["severity"], 1)
                    for o in opinions for r in o["risks"])
    risk = max(0, 10 - risk_load)
    criticals = sum(1 for o in opinions for r in o["risks"]
                    if r["severity"] == "critical")

    dims = {"Novelty": novelty, "Rigour": rigour, "Feasibility": feas,
            "Impact": impact, "Governance-fit": gov_fit, "Risk": risk}
    mean = sum(dims.values()) / len(dims)

    if criticals >= 2 or mean < 4.5:
        rec = "reject"
    elif mean >= 7.0 and criticals == 0:
        rec = "accept"
    else:
        rec = "revise"

    citations = []
    seen = set()
    for o in opinions:
        for r in o["references"]:
            key = r["title"]
            if key not in seen:
                seen.add(key)
                citations.append({"expert": o["expert_name"], **r})

    top_risks = sorted(
        (r for o in opinions for r in o["risks"]),
        key=lambda r: SEVERITY_W.get(r["severity"], 1), reverse=True)[:5]

    return {"dimensions": dims, "mean": round(mean, 2),
            "recommendation": rec, "critical_risks": criticals,
            "top_risks": top_risks, "citations": citations}
