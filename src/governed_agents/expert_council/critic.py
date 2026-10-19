"""Critic: score each expert on five dimensions and assign a grade.

Dimensions: breadth, depth, grounding, vigilance, cultivation.
Grades: Novice (<0.35), Practitioner (<0.55), Senior (<0.75), Principal (>=0.75).
"""

GRADES = [(0.35, "Novice"), (0.55, "Practitioner"), (0.75, "Senior"), (2.0, "Principal")]

DIMS = ["breadth", "depth", "grounding", "vigilance", "cultivation"]


def grade_of(score):
    for bound, name in GRADES:
        if score < bound:
            return name
    return "Principal"


class Critic:
    def __init__(self, opinion_history=None):
        # opinion_history: expert_id -> list of opinions (for vigilance)
        self.history = opinion_history if opinion_history is not None else {}

    def score(self, expert):
        breadth = min(1.0, len(expert.concepts) / 12.0)
        depth = min(1.0, len(expert.lenses) / 8.0)
        grounding = min(1.0, len(expert.references) / 8.0)
        kb_vigil = min(1.0, len(expert.risks) / 8.0)
        hist = self.history.get(expert.id, [])
        flag_rate = (sum(len(o["risks"]) for o in hist) / max(1, len(hist))) / 3.0
        vigilance = min(1.0, 0.6 * kb_vigil + 0.4 * min(1.0, flag_rate))
        cultivation = min(1.0, expert.training_items / 6.0)
        dims = {"breadth": round(breadth, 3), "depth": round(depth, 3),
                "grounding": round(grounding, 3),
                "vigilance": round(vigilance, 3),
                "cultivation": round(cultivation, 3)}
        overall = round(sum(dims.values()) / len(dims), 3)
        return {"dimensions": dims, "overall": overall, "grade": grade_of(overall)}
