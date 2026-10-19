"""Knowledge-graph-augmented Q&A.

Nodes: experts, concepts, lenses, risks, references, agent patterns.
Edges link experts to their knowledge and concepts to the experts that
hold them. Retrieval is keyword-overlap scoring; answering is either via
an optional `prompt -> text` LLM callable (cited) or a deterministic
grounded synthesis fallback.
"""

import re


def _toks(text):
    return set(re.findall(r"[a-z]{3,}", text.lower()))


class KnowledgeGraph:
    def __init__(self, experts, patterns):
        self.nodes = {}   # node_id -> {kind, label, text, expert}
        self.edges = []   # (src, dst, rel)
        for spec in experts:
            eid = "expert:" + spec["id"]
            self.nodes[eid] = {"kind": "expert", "label": spec["name"],
                               "text": spec["name"] + " " + spec["blurb"],
                               "expert": spec["id"]}
            for c in spec["concepts"]:
                nid = "concept:" + c
                self.nodes.setdefault(nid, {"kind": "concept", "label": c,
                                            "text": c, "expert": spec["id"]})
                self.edges.append((eid, nid, "knows"))
            for i, lens in enumerate(spec["lenses"]):
                nid = "lens:%s:%d" % (spec["id"], i)
                self.nodes[nid] = {"kind": "lens", "label": lens,
                                   "text": lens, "expert": spec["id"]}
                self.edges.append((eid, nid, "asks"))
            for risk in spec["risks"]:
                nid = "risk:" + risk["name"]
                if nid not in self.nodes:
                    self.nodes[nid] = {"kind": "risk", "label": risk["name"],
                                       "text": risk["name"] + ". " + risk["note"],
                                       "expert": spec["id"]}
                self.edges.append((eid, nid, "watches"))
            for ref in spec["references"]:
                nid = "ref:" + ref["title"]
                if nid not in self.nodes:
                    self.nodes[nid] = {"kind": "reference",
                                       "label": "%s (%s, %d)" % (ref["title"], ref["venue"], ref["year"]),
                                       "text": ref["title"] + " " + ref["venue"],
                                       "expert": spec["id"]}
                self.edges.append((eid, nid, "cites"))
        for i, p in enumerate(patterns):
            nid = "pattern:%d" % i
            self.nodes[nid] = {"kind": "pattern", "label": p["name"],
                               "text": p["name"] + ". Use: " + p["use"] + " Risks: " + p["risks"],
                               "expert": "agents"}
            self.edges.append(("expert:agents", nid, "catalogues"))

    def retrieve(self, question, top_k=8):
        q = _toks(question)
        scored = []
        for nid, node in self.nodes.items():
            nt = _toks(node["text"])
            overlap = len(q & nt)
            # phrase bonus for multi-word labels
            label = node["label"].lower()
            if len(label.split()) > 1 and label in question.lower():
                overlap += 3
            if overlap:
                scored.append((overlap, nid))
        scored.sort(reverse=True)
        return [(nid, self.nodes[nid], s) for s, nid in scored[:top_k]]

    def answer(self, question, llm=None, top_k=8):
        hits = self.retrieve(question, top_k=top_k)
        brief = self._brief(question, hits)
        citations = sorted({n["label"] for _, n, _ in hits if n["kind"] == "reference"})
        if llm is not None:
            prompt = ("Answer the question using only the grounded context below; "
                      "cite sources by title.\n\nContext:\n%s\n\nQuestion: %s"
                      % (brief, question))
            return {"question": question, "answer": llm(prompt),
                    "citations": citations, "mode": "llm-augmented",
                    "retrieved": [nid for nid, _, _ in hits]}
        return {"question": question, "answer": brief,
                "citations": citations, "mode": "grounded-synthesis",
                "retrieved": [nid for nid, _, _ in hits]}

    def _brief(self, question, hits):
        by_kind = {}
        for nid, node, score in hits:
            by_kind.setdefault(node["kind"], []).append((node, score))
        lines = ["Grounded brief for: %s" % question, ""]
        order = ["concept", "lens", "risk", "pattern", "reference", "expert"]
        titles = {"concept": "Relevant concepts", "lens": "Evaluation lenses to apply",
                  "risk": "Risk flags to check", "pattern": "Architecture patterns",
                  "reference": "Canonical references", "expert": "Consult these experts"}
        for kind in order:
            items = by_kind.get(kind, [])
            if not items:
                continue
            lines.append(titles[kind] + ":")
            for node, _ in items[:4]:
                lines.append("  - " + node["label"])
            lines.append("")
        return "\n".join(lines).strip()
