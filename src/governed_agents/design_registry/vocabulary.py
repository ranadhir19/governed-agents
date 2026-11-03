"""Fixed vocabulary for the design registry.

No project invents its own terms: project types, features and
environments come from these lists only. Unknown terms are rejected
at save time with an actionable message.
"""

PROJECT_TYPES = (
    "ai-assistant-rollout",
    "use-case-intake",
    "governance-console",
    "twin-configuration",
    "core-governance",
)

FEATURES = (
    "reporting",
    "multi-factor-auth",
    "project-launch",
    "monitoring",
)

ENVIRONMENTS = (
    "dev",
    "production",
)

STORE_VERSION = 1
