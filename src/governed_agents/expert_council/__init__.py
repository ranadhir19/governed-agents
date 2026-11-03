"""Expert council: an orchestrated multi-agent expert reference system."""

from .classify import classify
from .critic import Critic, grade_of
from .experts import Expert
from .kg import KnowledgeGraph
from .knowledge import AGENT_PATTERNS, CURRICULUM, DEMO_QUESTIONS, EXPERTS
from .parse import parse_material
from .registry import Registry
from .router import route
from .trainer import Trainer
from .verdict import synthesise

__all__ = [
    "AGENT_PATTERNS", "CURRICULUM", "DEMO_QUESTIONS", "EXPERTS",
    "Critic", "Expert", "KnowledgeGraph", "Registry", "Trainer",
    "classify", "grade_of", "parse_material", "route", "synthesise",
]
