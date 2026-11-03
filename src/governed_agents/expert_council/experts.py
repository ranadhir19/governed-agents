"""Domain experts: each produces a deterministic opinion on routed material.

An opinion contains: lenses answered (with verdict + evidence), risks
flagged, references cited, and added context.
"""

import re


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 12]


def _evidence_for(keywords, sentences, need=2):
    scored = []
    for s in sentences:
        low = s.lower()
        hits = sum(1 for k in keywords if k in low)
        if hits >= need:
            scored.append((hits, s))
    scored.sort(reverse=True)
    return [s for _, s in scored[:2]]


class Expert:
    def __init__(self, spec):
        self.spec = spec
        self.id = spec["id"]
        self.name = spec["name"]
        # working copies grow through training; registry records every change
        self.concepts = list(spec["concepts"])
        self.lenses = list(spec["lenses"])
        self.risks = [dict(r) for r in spec["risks"]]
        self.references = [dict(r) for r in spec["references"]]
        self.training_items = 0

    # -- knowledge growth -------------------------------------------------
    def add_concept(self, concept):
        if concept not in self.concepts:
            self.concepts.append(concept)
        self.training_items += 1

    def add_lens(self, lens):
        if lens not in self.lenses:
            self.lenses.append(lens)
        self.training_items += 1

    def add_risk(self, risk):
        if all(r["name"] != risk["name"] for r in self.risks):
            self.risks.append(dict(risk))
        self.training_items += 1

    def add_reference(self, ref):
        if all(r["title"] != ref["title"] for r in self.references):
            self.references.append(dict(ref))
        self.training_items += 1

    # -- opinion ----------------------------------------------------------
    def opine(self, material):
        text = material["text"]
        sentences = _sentences(text)
        methods = (material.get("methods") or "").lower()

        lens_answers = []
        for lens in self.lenses:
            kws = [w for w in re.findall(r"[a-z]{4,}", lens.lower())
                   if w not in {"does", "what", "with", "from", "this", "that"}]
            ev = _evidence_for(kws, sentences)
            # verdict from method-section support + evidence
            method_hits = sum(1 for k in kws if k in methods)
            if ev and method_hits >= 1:
                verdict = "addressed"
            elif ev or method_hits >= 1:
                verdict = "partial"
            else:
                verdict = "unaddressed"
            lens_answers.append({"lens": lens, "verdict": verdict,
                                 "evidence": ev[:1]})

        flagged = []
        low = text.lower()
        for risk in self.risks:
            triggers = [t for t in risk["triggers"] if t in low]
            if triggers:
                flagged.append({"risk": risk["name"], "severity": risk["severity"],
                                "note": risk["note"], "triggers": triggers[:2]})

        # references: rank by concept overlap with material tokens
        tset = material["token_set"]
        ranked = []
        for ref in self.references:
            title_words = set(re.findall(r"[a-z]{4,}", ref["title"].lower()))
            overlap = len(title_words & tset)
            ranked.append((overlap, ref))
        ranked.sort(key=lambda p: p[0], reverse=True)
        cited = [{"title": r["title"], "venue": r["venue"], "year": r["year"]}
                 for _, r in ranked[:2]]

        # added context from top matched concepts
        ctx_bits = []
        for concept in self.concepts:
            words = [w for w in concept.split() if len(w) > 2]
            if words and all(w in tset for w in words):
                ctx_bits.append(concept)
        context = (
            "Relevant %s concepts present in the material: %s. "
            % (self.name, ", ".join(ctx_bits[:4]))
            if ctx_bits else
            "No direct %s concept matches; review applies general principles. " % self.name
        )
        context += "Flagged %d risk pattern(s); answered %d lens(es)." % (
            len(flagged), len(lens_answers))

        return {
            "expert_id": self.id,
            "expert_name": self.name,
            "lenses": lens_answers,
            "risks": flagged,
            "references": cited,
            "context": context,
        }
