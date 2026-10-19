"""Policy-compliance checker.

Architecture policy is DATA (JSON), admin-editable: a list of rules, each
with an id, name, description, severity, a trigger condition over the
requirement, and a required pattern (or pattern set) that must appear in
the blueprint. The checker never invents policy; it evaluates the JSON.
"""

import json
from typing import Any, Dict, List

from .models import Pattern, PolicyResult, Requirement

DEFAULT_POLICY: Dict[str, Any] = {
    "policy_name": "Default governed-architecture policy",
    "version": "1.0",
    "rules": [
        {
            "id": "genai-model-gateway",
            "name": "Generative AI must route through a model gateway",
            "description": "Any generative-AI pattern requires a model gateway for "
                           "routing, rate limiting, spend control, and audit.",
            "severity": "high",
            "trigger": {"ai_ml_any_of": [
                "Retrieval-augmented generation (RAG)",
                "Supervised fine-tuning",
                "Prompt engineering and in-context learning",
                "Guardrailed generation"]},
            "requires_any_of": ["Model gateway and router"],
            "message": "Generative AI selected without a model gateway: no central "
                       "point for safety policy, cost control, or audit.",
        },
        {
            "id": "pii-redaction",
            "name": "PII in scope requires redaction before model input",
            "description": "When PII is in scope, the AI/ML layer must include "
                           "PII redaction / guardrailed generation.",
            "severity": "high",
            "trigger": {"requirement_field_contains": {
                "field": "data_sensitivity", "values": ["PII"]}},
            "requires_any_of": ["Guardrailed generation"],
            "message": "PII in scope but the AI/ML layer has no redaction/guardrail pattern.",
        },
        {
            "id": "agent-tool-governance",
            "name": "Agentic tool access must be governed",
            "description": "Any agentic pattern with tool use requires guardrailed "
                           "(least-privilege, scoped) tool access.",
            "severity": "high",
            "trigger": {"agentic_any_of": [
                "Single ReAct agent",
                "Orchestrator-workers",
                "Parallel fan-out",
                "Evaluator-optimiser loop",
                "Router to specialist agents",
                "Multi-agent debate and consensus",
                "Shared blackboard collaboration",
                "Human-in-the-loop escalation"]},
            "requires_any_of": ["Guardrailed tool access"],
            "message": "Agentic patterns selected without guardrailed tool access: "
                       "confused-deputy and prompt-injection blast radius is unbounded.",
        },
        {
            "id": "env-isolation",
            "name": "Production isolation with promotion-only flows",
            "description": "Production workloads need environment isolation; promotion "
                           "between environments must be explicit, never direct mutation.",
            "severity": "medium",
            "trigger": {"requirement_field_contains": {
                "field": "deployment_target", "values": ["cloud", "hybrid"]}},
            "requires_any_of": ["Landing zone with account vending",
                                "Fully managed platform services"],
            "message": "No governed landing-zone / managed-platform pattern: environment "
                       "isolation and promotion flows are not architecturally enforced.",
        },
        {
            "id": "tamper-evident-audit",
            "name": "Tamper-evident audit for regulated or PII workloads",
            "description": "Regulated or PII-bearing workloads require a tamper-evident "
                           "audit trail; the event backbone doubles as the audit source.",
            "severity": "medium",
            "trigger": {"requirement_field_contains": {
                "field": "compliance", "values": ["PCI", "HIPAA", "SOC", "GDPR"]}},
            "requires_any_of": ["Event-driven architecture",
                                "Change-data-capture streaming pipeline",
                                "Kappa architecture (streaming-only)"],
            "message": "Regulated workload without an event/CDC backbone to source a "
                       "tamper-evident audit trail from.",
        },
        {
            "id": "approved-egress",
            "name": "External calls restricted to approved egress",
            "description": "Agentic and edge patterns that call outward must do so "
                           "through approved egress with an allow-list.",
            "severity": "medium",
            "trigger": {"agentic_any_of": [
                "Single ReAct agent",
                "Orchestrator-workers",
                "Router to specialist agents"]},
            "requires_any_of": ["API gateway with backend services",
                                "Guardrailed tool access"],
            "message": "Outward-calling agentic patterns without a gateway or tool "
                       "governance layer to enforce approved egress.",
        },
    ],
}


def load_policy(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_policy(policy: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(policy, fh, indent=2)


def _field_contains(requirement: Requirement, field: str, values: List[str]) -> bool:
    val = getattr(requirement, field, None) or ""
    low = val.lower()
    return any(v.lower() in low for v in values)


class PolicyChecker:
    """Evaluates a blueprint against a JSON policy."""

    def __init__(self, policy: Dict[str, Any] = None):
        self.policy = policy if policy is not None else DEFAULT_POLICY

    def check(self, blueprint: Dict[str, Pattern],
              requirement: Requirement) -> List[PolicyResult]:
        names = {p.name for p in blueprint.values()}
        results: List[PolicyResult] = []
        for rule in self.policy.get("rules", []):
            trigger = rule.get("trigger", {})
            fires = False
            if "ai_ml_any_of" in trigger:
                pick = blueprint.get("ai_ml")
                fires = bool(pick and pick.name in trigger["ai_ml_any_of"])
            elif "agentic_any_of" in trigger:
                pick = blueprint.get("agentic")
                fires = bool(pick and pick.name in trigger["agentic_any_of"])
            elif "requirement_field_contains" in trigger:
                spec = trigger["requirement_field_contains"]
                fires = _field_contains(requirement, spec["field"], spec["values"])
            if not fires:
                continue
            satisfied = any(n in names for n in rule.get("requires_any_of", []))
            results.append(PolicyResult(
                rule_id=rule["id"], rule_name=rule["name"],
                passed=satisfied, severity=rule.get("severity", "medium"),
                message=("PASS: " + rule["name"]) if satisfied else
                        (f"VIOLATION [{rule['severity'].upper()}]: {rule['message']} "
                         f"(rule: {rule['id']})")))
        return results
