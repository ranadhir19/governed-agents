"""Chief architect orchestrator.

Demonstrates the agentic patterns the board recommends: routing (requirement
-> specialist sub-briefs), orchestrator-workers (chief -> five specialists),
parallelisation (specialists score concurrently), evaluator-optimiser (critic
loop with swaps), and a shared blackboard. Every step is logged.
"""

import zlib
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import numpy as np

from .adr import render_adr
from .blackboard import Blackboard
from .critic import DesignCritic
from .inputs import check_missing, parse_document
from .models import (DOMAIN_LABELS, BoardResult, Finding, Pattern, Priorities,
                     Requirement, ScoredPattern)
from .patterns import CATALOGUES, find_pattern
from .policy import PolicyChecker
from .specialists import Specialist, all_specialists


class ChiefArchitect:
    def __init__(self, seed: int = 7,
                 policy_checker: Optional[PolicyChecker] = None,
                 max_critic_iterations: int = 2):
        self.seed = seed
        self.specialists = all_specialists()
        self.critic = DesignCritic()
        self.policy_checker = policy_checker or PolicyChecker()
        self.max_critic_iterations = max_critic_iterations

    def run(self, requirement: Requirement, priorities: Priorities,
            document_text: Optional[str] = None) -> BoardResult:
        log: List[str] = []
        board = Blackboard()
        rng = np.random.default_rng(self.seed)

        # 1. input intake (structured fields or parsed document)
        if document_text:
            requirement, notes = parse_document(document_text)
            log.append(f"[intake] parsed document; extracted: {notes or 'nothing usable'}")
        else:
            log.append("[intake] structured requirement received")

        # 2. input integrity: missing info is reported, never inferred
        missing = check_missing(requirement)
        log.append(f"[intake] missing-information checklist: {len(missing)} item(s)")
        board.post("chief-architect", "missing_info", missing)

        # 3. route: decompose into per-domain sub-briefs
        for spec in self.specialists:
            log.append(f"[route] {spec.label} <- sub-brief dispatched")

        # 4. parallel specialist scoring (orchestrator-workers, parallelised)
        ranked: Dict[str, List[ScoredPattern]] = {}

        def _work(spec: Specialist):
            # stable per-domain stream: crc32, NOT hash() (hash() is salted per process)
            sub_rng = np.random.default_rng(
                (self.seed + zlib.crc32(spec.domain.encode())) % (2 ** 31))
            scored = spec.score(requirement, priorities, sub_rng)
            board.post(spec.label, "ranked_patterns",
                       [(s.pattern.name, round(s.fit, 3)) for s in scored])
            return spec.domain, scored

        with ThreadPoolExecutor(max_workers=5) as ex:
            for domain, scored in ex.map(_work, self.specialists):
                ranked[domain] = scored
        log.append("[workers] all 5 specialists scored their catalogues (parallel)")

        # 5. assemble blueprint from top picks
        blueprint: Dict[str, Pattern] = {d: ranked[d][0].pattern for d in ranked}
        history = [{d: p.name for d, p in blueprint.items()}]
        log.append("[aggregate] blueprint assembled from top-ranked pattern per layer")

        # 6. evaluator-optimiser: critic loop with swaps
        findings: List[Finding] = []
        initial_findings: List[Finding] = []
        iterations = 0
        for i in range(self.max_critic_iterations):
            iterations = i + 1
            findings = self.critic.evaluate(blueprint, requirement)
            if i == 0:
                initial_findings = list(findings)
            board.post("design-critic", f"findings_iter_{i + 1}",
                       [(f.severity, f.category) for f in findings])
            log.append(f"[critic] iteration {i + 1}: {len(findings)} finding(s) "
                       f"({sum(1 for f in findings if f.severity == 'high')} high)")
            swap = next((f for f in findings if f.suggested_swap), None)
            if not swap:
                break
            try:
                new_pat = find_pattern(swap.suggested_swap)
            except KeyError:
                break
            old = blueprint[new_pat.domain].name
            blueprint[new_pat.domain] = new_pat
            history.append({d: p.name for d, p in blueprint.items()})
            log.append(f"[optimiser] swapped '{old}' -> '{new_pat.name}' "
                       f"({new_pat.domain}); re-running critic")
        findings = self.critic.evaluate(blueprint, requirement)
        log.append(f"[critic] final: {len(findings)} finding(s) remain")

        # 7. policy compliance
        policy_results = self.policy_checker.check(blueprint, requirement)
        n_viol = sum(1 for r in policy_results if not r.passed)
        log.append(f"[policy] {len(policy_results)} rule(s) triggered, {n_viol} violation(s)")

        # 8. trade-off narratives
        tradeoffs = {d: self._tradeoff(d, ranked[d]) for d in ranked}

        result = BoardResult(
            requirement=requirement, priorities=priorities,
            missing_info=missing, ranked=ranked, blueprint=blueprint,
            blueprint_history=history, tradeoffs=tradeoffs,
            critic_findings=findings, critic_iterations=iterations,
            initial_findings=initial_findings,
            policy_results=policy_results, adr_markdown="",
            workflow_log=log)
        result.adr_markdown = render_adr(result)
        log.append("[adr] architecture decision record rendered")
        return result

    @staticmethod
    def _tradeoff(domain: str, ranked: List[ScoredPattern]) -> str:
        top, second = ranked[0], ranked[1]
        gap = top.fit - second.fit
        top_weak = min(top.pattern.scores, key=lambda d: top.pattern.scores[d])
        sec_strong = max(second.pattern.scores, key=lambda d: second.pattern.scores[d])
        return (f"{top.pattern.name} leads {second.pattern.name} by {gap:.2f} fit points. "
                f"Watch {top.pattern.name}'s weakest dimension ({top_weak}); "
                f"{second.pattern.name} is stronger there ({sec_strong}). "
                f"If priorities shift toward {top_weak}, re-run the board.")
