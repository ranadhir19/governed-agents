"""Design critic: stress-tests the combined blueprint.

Checks: over-engineering, conflicting / anti-pattern combinations,
resilience gaps, and consistency gaps. Findings carry severity and, where a
safe alternative exists, a suggested_swap the orchestrator's optimiser loop
may apply (evaluator-optimiser, max 2 iterations).
"""

from typing import Dict, List, Optional

from .models import Finding, Pattern, Requirement
from .patterns import find_pattern

# (pattern A, pattern B, message, suggestion, severity) - cross-domain clashes
CONFLICT_PAIRS = [
    ("Kappa architecture (streaming-only)", "Batch inference pipeline",
     "A streaming-only data tier feeding a batch inference pipeline: fresh data "
     "waits for the next batch run, so the streaming investment buys nothing.",
     "Make inference streaming/micro-batch, or relax the data tier to lakehouse.",
     "medium"),
    ("Multi-region active-active", "Central data warehouse",
     "Active-active serving needs multi-region data; a single-region warehouse "
     "becomes the consistency bottleneck and the blast radius.",
     "Pair active-active serving with a multi-region-capable data substrate.",
     "high"),
    ("Multi-region active-active", "Batch inference pipeline",
     "Paying for active-active serving while the ML tier is batch is inconsistent: "
     "the system is only as fresh as its slowest tier.",
     "Downgrade serving to active-passive or make inference real-time.",
     "medium"),
    ("Edge deployment", "Central data warehouse",
     "Edge serving with a central warehouse forces every request back to origin; "
     "the latency win evaporates.",
     "Serve from edge-cached features or a distributed data tier.",
     "medium"),
    ("Serverless functions", "Real-time inference endpoint",
     "Serverless cold starts fight a real-time inference SLO; the two scaling "
     "models pull in opposite directions at sustained load.",
     "Use provisioned inference capacity for the hot path; serverless for the rest.",
     "medium"),
    ("Modular monolith", "Data mesh",
     "A monolith's team topology contradicts data mesh's domain-team ownership; "
     "one of the two will be fiction within a year.",
     "Align the org model first, then pick the matching architecture.",
     "medium"),
]

GENERATIVE_AI = {
    "Retrieval-augmented generation (RAG)",
    "Supervised fine-tuning",
    "Prompt engineering and in-context learning",
    "Guardrailed generation",
}


def _mentions(text: Optional[str], *needles: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(n.lower() in low for n in needles)


def _throughput_number(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    import re
    m = re.search(r"(\d[\d,]*)", text.replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


class DesignCritic:
    """Evaluates a blueprint; the orchestrator may iterate on its findings."""

    def evaluate(self, blueprint: Dict[str, Pattern],
                 requirement: Requirement) -> List[Finding]:
        findings: List[Finding] = []
        names = {p.name for p in blueprint.values()}

        # 1. over-engineering: too many low-simplicity picks
        complex_picks = [p for p in blueprint.values() if p.scores["simplicity"] <= 4]
        if len(complex_picks) >= 3:
            weakest = min(complex_picks,
                          key=lambda p: p.scores["simplicity"])
            alt = max(
                (q for q in self._catalogue_of(weakest.domain)
                 if q.name not in names and q.scores["simplicity"] >= 6),
                key=lambda q: q.scores["simplicity"], default=None)
            findings.append(Finding(
                severity="high", category="over-engineering",
                message=(f"{len(complex_picks)} of 5 layers chose high-complexity patterns "
                         f"({', '.join(p.name for p in complex_picks)}). The combined "
                         f"operational burden likely exceeds the team's capacity."),
                suggestion=(f"Simplify the weakest link first: replace '{weakest.name}' "
                            f"with a simpler pattern in the same layer."),
                suggested_swap=alt.name if alt else None))

        # 2. conflicting combinations
        for a, b, msg, sug, sev in CONFLICT_PAIRS:
            if a in names and b in names:
                findings.append(Finding(severity=sev, category="conflict",
                                        message=msg, suggestion=sug))

        # 3. resilience gaps
        cloud = blueprint.get("cloud")
        if cloud and cloud.name == "Single-region multi-zone deployment":
            if _mentions(requirement.availability_target, "99.99", "99.999"):
                findings.append(Finding(
                    severity="high", category="resilience",
                    message=("Availability target implies surviving more than zone failures, "
                             "but the cloud layer is single-region."),
                    suggestion="Move to active-passive DR or active-active, or relax the target."))

        tput = _throughput_number(requirement.throughput)
        soft = blueprint.get("software")
        data = blueprint.get("data")
        async_present = (soft and soft.name in ("Event-driven architecture",)) or \
                        (data and data.name in ("Kappa architecture (streaming-only)",
                                                "Change-data-capture streaming pipeline"))
        if tput and tput >= 5000 and not async_present:
            findings.append(Finding(
                severity="medium", category="resilience",
                message=(f"Throughput ~{tput:,.0f}/s with no async buffering layer; "
                         "traffic spikes will translate directly into latency spikes or drops."),
                suggestion="Add an event backbone or streaming buffer in front of the hot path."))

        # 4. consistency gaps
        if cloud and cloud.name == "Edge deployment" and data and data.name != "Feature store":
            findings.append(Finding(
                severity="medium", category="consistency",
                message=("Edge serving paired with a non-edge data tier: features must travel "
                         "back to origin, adding latency and freshness risk on the hot path."),
                suggestion=("Use a feature store with edge-cached features so scoring "
                            "does not round-trip to origin."),
                suggested_swap="Feature store"))
        if cloud and cloud.name == "Multi-region active-active":
            if data and data.name in ("Central data warehouse", "Data lake"):
                findings.append(Finding(
                    severity="high", category="consistency",
                    message=("Active-active serving over a single-writer data tier guarantees "
                             "cross-region write conflicts or stale reads."),
                    suggestion="Adopt a multi-writer data tier or downgrade to active-passive."))

        # 4b. prediction-task fit: retrieval-only AI/ML cannot score or predict
        ai_pick = blueprint.get("ai_ml")
        if ai_pick and ai_pick.name == "Embedding-based semantic search":
            if _mentions(requirement.problem,
                         "scor", "predict", "fraud", "classif", "detect"):
                findings.append(Finding(
                    severity="medium", category="consistency",
                    message=("The problem requires producing predictions/scores, but the "
                             "AI/ML layer selected a retrieval-only pattern: semantic "
                             "search finds similar items, it does not score them."),
                    suggestion=("Use a real-time inference endpoint for the scoring "
                                "model; keep semantic search only if a lookup step exists."),
                    suggested_swap="Real-time inference endpoint"))

        # 5. team-size vs complexity (only when the team size is actually known)
        if _mentions(requirement.team_size, "1", "2", "3", "4", "5"):
            import re
            m = re.search(r"(\d+)", requirement.team_size or "")
            small = m and int(m.group(1)) <= 5
            if small and any(p.name == "Microservices" for p in blueprint.values()):
                findings.append(Finding(
                    severity="high", category="over-engineering",
                    message=("A team of ~5 or fewer running microservices will spend more "
                             "on platform toil than on product."),
                    suggestion="Start with a modular monolith; extract services when a boundary earns it.",
                    suggested_swap="Modular monolith"))
        return findings

    def _catalogue_of(self, domain: str):
        from .patterns import CATALOGUES
        return CATALOGUES[domain]
