"""Work twin: a principal-split worker twin with measured discretion."""

from .planes import Plane, Record, UpOnlyStore
from .twins import PersonalTwin, ProfessionalTwin, WorkingTwin, ActionProposal
from .cohort import cohort_table, task_type_summary, Cell
from .discretion import (measure_discretion, task_profile, arithmetic_dimensions,
                         FieldSpec, DiscretionResult, MIN_MARGIN, MIN_MINORITY)
from .shadow import ShadowLog, temporal_holdout
from .ladder import Level, SkillState, evaluate_step, advance, LEVEL_NAMES
from .generate import generate, generate_shadow_cases, TASK_TYPES, FIELD_SPECS
from .proof import deployment_gate

__all__ = [
    "Plane", "Record", "UpOnlyStore",
    "PersonalTwin", "ProfessionalTwin", "WorkingTwin", "ActionProposal",
    "cohort_table", "task_type_summary", "Cell",
    "measure_discretion", "task_profile", "arithmetic_dimensions",
    "FieldSpec", "DiscretionResult", "MIN_MARGIN", "MIN_MINORITY",
    "ShadowLog", "temporal_holdout",
    "Level", "SkillState", "evaluate_step", "advance", "LEVEL_NAMES",
    "generate", "generate_shadow_cases", "TASK_TYPES", "FIELD_SPECS",
    "deployment_gate",
]
