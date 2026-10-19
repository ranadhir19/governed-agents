"""Classify which expert domains a material touches (keyword coverage)."""


def concept_hits(concepts, token_set):
    """Count concepts whose significant words all appear in the material."""
    hits = []
    for concept in concepts:
        words = [w for w in concept.lower().split() if len(w) > 2]
        if words and all(w in token_set for w in words):
            hits.append(concept)
    return hits


def classify(material, experts, threshold=0.12):
    """Score every expert by concept coverage; return sorted (id, score, hits)."""
    token_set = material["token_set"]
    scored = []
    for spec in experts:
        hits = concept_hits(spec["concepts"], token_set)
        score = len(hits) / max(1, len(spec["concepts"]))
        # lens keyword support: fraction of lens words present adds a small boost
        lens_words = set()
        for lens in spec["lenses"]:
            lens_words.update(w for w in lens.lower().split() if len(w) > 3)
        lens_cov = len(lens_words & token_set) / max(1, len(lens_words))
        score = 0.8 * score + 0.2 * lens_cov
        scored.append({"id": spec["id"], "name": spec["name"],
                       "score": round(score, 3), "hits": hits})
    scored.sort(key=lambda d: d["score"], reverse=True)
    touched = [d for d in scored if d["score"] >= threshold]
    return {"all": scored, "touched": touched}
