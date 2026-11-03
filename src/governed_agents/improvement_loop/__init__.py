"""Autonomous critic-gated improvement loop for long-running agents.

A person sets the task, quality standard, budget and human gates once up
front; the orchestrator then drives propose -> critique -> diagnose ->
revise -> repeat with no per-iteration prompting.
"""

from .ledger import AuditLedger
from .critics import (
    ChecklistItem,
    Critic,
    CriticResult,
    CriticPanel,
    PanelResult,
    build_default_panel,
)
from .diagnostician import Directive, Diagnostician, Reviser, propose_plan
from .checkpoints import Checkpoint, CheckpointManager, CheckpointError, StateClass
from .healing import (
    FaultCategory,
    Fault,
    Investigator,
    Healer,
    RecoveryReport,
    GoalDriftMonitor,
)
from .engine import LoopConfig, Termination, ImprovementEngine, RunReport

__all__ = [
    "AuditLedger",
    "ChecklistItem",
    "Critic",
    "CriticResult",
    "CriticPanel",
    "PanelResult",
    "build_default_panel",
    "Directive",
    "Diagnostician",
    "Reviser",
    "propose_plan",
    "Checkpoint",
    "CheckpointManager",
    "CheckpointError",
    "StateClass",
    "FaultCategory",
    "Fault",
    "Investigator",
    "Healer",
    "RecoveryReport",
    "GoalDriftMonitor",
    "LoopConfig",
    "Termination",
    "ImprovementEngine",
    "RunReport",
]
