"""Data models for the architecture board.

All scores use a 0-10 scale where HIGHER is always better:
  cost         10 = very cheap to build and run
  latency      10 = very low latency
  scalability  10 = scales effortlessly
  robustness   10 = very resilient to failure
  integration  10 = easy to integrate with other systems
  simplicity   10 = very simple to build and operate
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DIMENSIONS = ["cost", "latency", "scalability", "robustness", "integration", "simplicity"]

DOMAINS = ["software", "cloud", "ai_ml", "data", "agentic"]

DOMAIN_LABELS = {
    "software": "Software Architecture",
    "cloud": "Cloud & Infrastructure",
    "ai_ml": "AI / Machine Learning",
    "data": "Data Platform",
    "agentic": "Agentic Systems",
}


@dataclass
class Pattern:
    """One architecture pattern from a specialist's catalogue."""
    name: str
    domain: str
    description: str
    pros: List[str]
    cons: List[str]
    when_to_use: str
    poor_fit_when: str
    scores: Dict[str, float]  # dimension -> 0..10


@dataclass
class Priorities:
    """Requester priorities, 1 (least important) to 5 (most important)."""
    cost: int = 3
    latency: int = 3
    scalability: int = 3
    robustness: int = 3
    integration: int = 3
    simplicity: int = 3

    def __post_init__(self):
        for dim in DIMENSIONS:
            v = getattr(self, dim)
            if not isinstance(v, int) or not 1 <= v <= 5:
                raise ValueError(f"priority '{dim}' must be an int in 1..5, got {v!r}")

    def weights(self) -> Dict[str, float]:
        return {dim: float(getattr(self, dim)) for dim in DIMENSIONS}


@dataclass
class Requirement:
    """Structured architecture requirement. Any field may be None.

    The board NEVER infers missing fields. Missing critical fields are
    reported through an explicit missing-information checklist.
    """
    title: str
    problem: str
    throughput: Optional[str] = None
    latency_budget: Optional[str] = None
    data_sensitivity: Optional[str] = None
    compliance: Optional[str] = None
    team_size: Optional[str] = None
    budget_posture: Optional[str] = None
    deployment_target: Optional[str] = None
    availability_target: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# (field name, why the board needs it)
REQUIRED_FIELDS = [
    ("throughput", "expected load (requests/s, events/s, batch volume) - needed to validate scalability claims"),
    ("latency_budget", "latency target (e.g. p99 < 200ms) - needed to validate latency-sensitive pattern choices"),
    ("data_sensitivity", "whether PII / sensitive data is in scope - needed for redaction and governance checks"),
    ("compliance", "regulatory regime (e.g. none, SOC 2, PCI DSS, HIPAA) - needed for policy compliance checks"),
    ("team_size", "delivery team size / maturity - needed to judge operability of complex patterns"),
    ("budget_posture", "cost sensitivity - needed to weigh build/run cost trade-offs"),
    ("deployment_target", "where it runs (cloud, on-prem, hybrid, edge) - needed for infrastructure pattern fit"),
    ("availability_target", "uptime target (e.g. 99.9%) - needed for resilience and redundancy decisions"),
]


@dataclass
class ScoredPattern:
    pattern: Pattern
    fit: float
    weighted_parts: Dict[str, float]  # dimension -> weight * score contribution


@dataclass
class Finding:
    severity: str  # high | medium | low
    category: str
    message: str
    suggestion: str
    suggested_swap: Optional[str] = None  # pattern name the optimiser may swap in


@dataclass
class PolicyResult:
    rule_id: str
    rule_name: str
    passed: bool
    severity: str
    message: str


@dataclass
class BoardResult:
    requirement: Requirement
    priorities: Priorities
    missing_info: List[str]
    ranked: Dict[str, List[ScoredPattern]]  # domain -> ranked patterns
    blueprint: Dict[str, Pattern]  # domain -> chosen pattern
    blueprint_history: List[Dict[str, str]]  # optimiser iterations
    tradeoffs: Dict[str, str]  # domain -> trade-off narrative
    critic_findings: List[Finding]
    critic_iterations: int
    policy_results: List[PolicyResult]
    adr_markdown: str
    workflow_log: List[str]
    initial_findings: List[Finding] = field(default_factory=list)
