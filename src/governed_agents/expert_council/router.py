"""Route material only to the relevant experts."""


def route(classification, experts_by_id, threshold=0.12, top_k=5):
    """Return [(Expert, score, hits)] for touched domains, capped at top_k."""
    picked = []
    for entry in classification["touched"][:top_k]:
        if entry["score"] >= threshold:
            picked.append((experts_by_id[entry["id"]], entry["score"], entry["hits"]))
    # always include at least the best-scoring expert
    if not picked and classification["all"]:
        best = classification["all"][0]
        picked.append((experts_by_id[best["id"]], best["score"], best["hits"]))
    return picked
