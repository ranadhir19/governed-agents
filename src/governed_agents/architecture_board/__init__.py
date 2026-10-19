"""Architecture board: a multi-agent advisory board for architecture decisions."""

from .adr import render_adr
from .blackboard import Blackboard
from .critic import DesignCritic
from .inputs import check_missing, parse_document
from .models import (DIMENSIONS, DOMAIN_LABELS, BoardResult, Finding, Pattern,
                     PolicyResult, Priorities, Requirement, ScoredPattern)
from .orchestrator import ChiefArchitect
from .patterns import CATALOGUES, total_patterns
from .policy import DEFAULT_POLICY, PolicyChecker, load_policy, save_policy
from .specialists import Specialist, all_specialists

__all__ = [
    "DIMENSIONS", "DOMAIN_LABELS", "BoardResult", "Finding", "Pattern",
    "PolicyResult", "Priorities", "Requirement", "ScoredPattern",
    "Blackboard", "ChiefArchitect", "DesignCritic", "PolicyChecker",
    "Specialist", "all_specialists", "CATALOGUES", "total_patterns",
    "DEFAULT_POLICY", "load_policy", "save_policy",
    "check_missing", "parse_document", "render_adr",
]
