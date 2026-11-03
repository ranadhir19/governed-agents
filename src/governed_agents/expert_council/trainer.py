"""Trainer: advance each expert by one curated curriculum item per cycle,
weakest critic dimension first. Every change is recorded in the registry.
"""

from .critic import DIMS


class Trainer:
    def __init__(self, curriculum, critic, registry):
        # curriculum: expert_id -> list of {dim, kind, payload}; consumed in order
        self.curriculum = {k: list(v) for k, v in curriculum.items()}
        self.critic = critic
        self.registry = registry

    def _apply(self, expert, item):
        kind, payload = item["kind"], item["payload"]
        if kind == "concept":
            expert.add_concept(payload)
        elif kind == "lens":
            expert.add_lens(payload)
        elif kind == "risk":
            expert.add_risk(payload)
        elif kind == "reference":
            expert.add_reference(payload)
        self.registry.append(expert.id, "training",
                             {"dim": item["dim"], "kind": kind, "payload": payload})

    def cycle(self, experts):
        """One training cycle over all experts. Returns per-expert reports."""
        reports = []
        for expert in experts:
            scores = self.critic.score(expert)["dimensions"]
            weakest = min(DIMS, key=lambda d: scores[d])
            pool = self.curriculum.get(expert.id, [])
            # prefer an item targeting the weakest dimension; else first remaining
            item = next((i for i in pool if i["dim"] == weakest), None)
            if item is None and pool:
                item = pool[0]
            if item is None:
                reports.append({"expert": expert.id, "trained": False,
                                "weakest": weakest})
                continue
            pool.remove(item)
            before = self.critic.score(expert)["overall"]
            self._apply(expert, item)
            after = self.critic.score(expert)["overall"]
            reports.append({"expert": expert.id, "trained": True,
                            "weakest": weakest, "item": item,
                            "before": before, "after": after})
        return reports
