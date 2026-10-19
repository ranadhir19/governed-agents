"""Architecture Decision Record renderer (markdown)."""

from datetime import date
from typing import Dict, List

from .models import (DOMAIN_LABELS, BoardResult, Finding, Pattern, PolicyResult,
                     Priorities, Requirement, ScoredPattern)


def render_adr(result: BoardResult) -> str:
    req = result.requirement
    pri = result.priorities
    L = []
    A = L.append
    A(f"# Architecture Decision Record: {req.title}")
    A("")
    A(f"Status: proposed | Date: {date.today().isoformat()} | Board: multi-agent architecture board")
    A("")
    A("## Context")
    A("")
    A(req.problem)
    A("")
    A("Known requirement fields:")
    for fname in ["throughput", "latency_budget", "data_sensitivity", "compliance",
                  "team_size", "budget_posture", "deployment_target", "availability_target"]:
        val = getattr(req, fname)
        A(f"- {fname}: {val if val else '(not provided)'}")
    A("")
    A("Priorities (1-5): " + ", ".join(
        f"{d}={getattr(pri, d)}" for d in
        ["cost", "latency", "scalability", "robustness", "integration", "simplicity"]))
    A("")
    A("## Decision")
    A("")
    for domain in ["software", "cloud", "ai_ml", "data", "agentic"]:
        pat = result.blueprint[domain]
        top = result.ranked[domain][0]
        A(f"### {DOMAIN_LABELS[domain]}: {pat.name} (fit {top.fit:.2f}/10)")
        A("")
        A(pat.description)
        A("")
        A(f"Rationale: highest weighted fit against the stated priorities; "
          f"key strengths are {', '.join(_top_dims(pat))}.")
        A("")
    A("## Alternatives considered")
    A("")
    for domain in ["software", "cloud", "ai_ml", "data", "agentic"]:
        ranked = result.ranked[domain]
        if len(ranked) > 1:
            alt = ranked[1]
            A(f"- {DOMAIN_LABELS[domain]}: {alt.pattern.name} (fit {alt.fit:.2f}) - "
              f"runner-up. {result.tradeoffs.get(domain, '')}")
    A("")
    A("## Trade-off analysis")
    A("")
    for domain in ["software", "cloud", "ai_ml", "data", "agentic"]:
        A(f"### {DOMAIN_LABELS[domain]}")
        A("")
        A(result.tradeoffs.get(domain, ""))
        A("")
    A("## Critic findings (evaluator-optimiser)")
    A("")
    A(f"Critic iterations: {result.critic_iterations}. "
      f"Optimiser applied {len(result.blueprint_history) - 1} swap(s).")
    A("")
    if result.critic_findings:
        for f in result.critic_findings:
            A(f"- [{f.severity.upper()}] ({f.category}) {f.message}")
            A(f"  Suggestion: {f.suggestion}")
    else:
        A("No findings: the blueprint survived the critic unchanged.")
    A("")
    A("## Policy compliance")
    A("")
    for pr in result.policy_results:
        A(f"- {'PASS' if pr.passed else 'VIOLATION'} [{pr.severity.upper()}] "
          f"{pr.rule_name}: {pr.message}")
    if not result.policy_results:
        A("No policy rules were triggered by this requirement.")
    A("")
    A("## Missing information (never inferred)")
    A("")
    if result.missing_info:
        for m in result.missing_info:
            A(f"- [ ] {m}")
    else:
        A("None: all critical fields were provided.")
    A("")
    A("## Consequences")
    A("")
    A("- The blueprint is a starting point: validate each pattern choice against "
      "the missing information above before committing build effort.")
    A("- Policy violations listed above must be remediated (add the required "
      "pattern or obtain a policy exception) before production approval.")
    A("- Re-run the board when priorities or requirement fields change; fit scores "
      "are priority-weighted and will shift.")
    A("")
    A("## References")
    A("")
    A("- Hohpe, G. & Woolf, B., Enterprise Integration Patterns (messaging and "
      "integration pattern vocabulary)")
    A("- Newman, S., Building Microservices (service decomposition trade-offs)")
    A("- Fowler, M., Patterns of Enterprise Application Architecture (layering, "
      "domain logic patterns)")
    A("- Kleppmann, M., Designing Data-Intensive Applications (data systems, "
      "consistency, and streaming trade-offs)")
    A("")
    return "\n".join(L)


def _top_dims(pat: Pattern, n: int = 2):
    return [d for d, _ in sorted(pat.scores.items(), key=lambda kv: kv[1], reverse=True)[:n]]
