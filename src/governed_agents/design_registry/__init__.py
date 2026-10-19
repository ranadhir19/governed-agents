"""Design registry: one record per governed delivery project.

One registry, one answer: each project has a single record holding its
design file location, requirements board, environment, application URL
and feature set. Storage is a plain JSON file plus validation.
"""

from .completeness import completeness
from .handoff import ROUTE_CAPABILITIES, build_handoff_contract, capability_routes
from .probe import probe_endpoint, probe_endpoints
from .registry import Registry
from .validation import (
    RegistryValidationError,
    detect_design_adapter,
    validate_project,
)
from .vocabulary import ENVIRONMENTS, FEATURES, PROJECT_TYPES

__all__ = [
    "Registry",
    "RegistryValidationError",
    "validate_project",
    "detect_design_adapter",
    "completeness",
    "probe_endpoint",
    "probe_endpoints",
    "build_handoff_contract",
    "capability_routes",
    "ROUTE_CAPABILITIES",
    "PROJECT_TYPES",
    "FEATURES",
    "ENVIRONMENTS",
]
