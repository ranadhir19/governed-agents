"""Validation for design-registry records.

Every rule refuses a bad save with an actionable message: the message
names the offending field, the offending value, and exactly what would
be accepted instead.
"""

import re
from urllib.parse import urlparse

from .vocabulary import ENVIRONMENTS, FEATURES, PROJECT_TYPES

FILE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{12,}$")


class RegistryValidationError(ValueError):
    """Raised when a record fails validation. The save is suppressed."""


def _is_http_url(value):
    try:
        parts = urlparse(value)
    except Exception:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def detect_design_adapter(design_location):
    """Return the design-tool adapter name for a design location.

    Figma is one supported adapter among generic concepts: a design-tool
    file link (any http(s) URL, adapter detected from the host) or a
    file key.
    """
    if _is_http_url(design_location):
        host = urlparse(design_location).netloc.lower()
        if "figma" in host:
            return "figma"
        return "generic-link"
    if FILE_KEY_RE.match(design_location or ""):
        return "file-key"
    return "unknown"


def validate_design_location(value):
    if not isinstance(value, str) or not value.strip():
        raise RegistryValidationError(
            "design_location: missing. Provide a design-tool file link "
            "(http(s) URL) or a file key (letters/digits, at least 12 characters)."
        )
    value = value.strip()
    if _is_http_url(value):
        return value
    if FILE_KEY_RE.match(value):
        return value
    raise RegistryValidationError(
        "design_location: %r is not a valid design-tool link or file key. "
        "Use an http(s) design-tool file link (e.g. https://<design-tool-host>/file/<id>) "
        "or a file key of at least 12 letters/digits." % value
    )


def validate_application_url(value, environment):
    if value is None or (isinstance(value, str) and not value.strip()):
        if environment == "production":
            raise RegistryValidationError(
                "application_url: missing, but environment is 'production'. "
                "Production entries must give the application URL people open "
                "(http(s) URL). Refusing the save."
            )
        return None
    value = value.strip()
    if not _is_http_url(value):
        raise RegistryValidationError(
            "application_url: %r is not a valid URL. "
            "Use an http:// or https:// URL, e.g. https://app.example.com/." % value
        )
    return value


def validate_features(features):
    if features is None:
        return {name: False for name in FEATURES}
    if isinstance(features, dict):
        items = features.items()
    elif isinstance(features, (list, tuple, set)):
        items = [(name, True) for name in features]
    else:
        raise RegistryValidationError(
            "features: expected a list of feature names or a name->bool mapping, "
            "got %r." % (features,)
        )
    normalized = {name: False for name in FEATURES}
    for name, enabled in items:
        if name not in FEATURES:
            raise RegistryValidationError(
                "features: unknown feature %r. Known features are: %s. "
                "Projects may not invent their own terms." % (name, ", ".join(FEATURES))
            )
        normalized[name] = bool(enabled)
    return normalized


def validate_mfa_exception(environment, features, mfa_exception):
    """Production without multi-factor-auth needs a deliberate recorded exception."""
    if environment != "production":
        return None
    if features.get("multi-factor-auth"):
        return None
    if not isinstance(mfa_exception, dict):
        raise RegistryValidationError(
            "mfa_exception: production project has no 'multi-factor-auth' feature "
            "and no recorded exception. Provide mfa_exception as a mapping with "
            "'reason' and 'approved_by' (and ideally 'expires'), or enable the "
            "'multi-factor-auth' feature. An insecure default is not accepted."
        )
    missing = [k for k in ("reason", "approved_by") if not mfa_exception.get(k)]
    if missing:
        raise RegistryValidationError(
            "mfa_exception: incomplete recorded exception, missing %s. "
            "Provide 'reason' and 'approved_by' so the exception is deliberate, not a default."
            % ", ".join(missing)
        )
    return {
        "reason": str(mfa_exception["reason"]),
        "approved_by": str(mfa_exception["approved_by"]),
        "expires": mfa_exception.get("expires"),
    }


def validate_project(record):
    """Validate a project record; return a normalized copy.

    Raises RegistryValidationError on any problem. Nothing is written
    when validation fails.
    """
    if not isinstance(record, dict):
        raise RegistryValidationError(
            "project: expected a mapping, got %r." % (record,)
        )
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RegistryValidationError(
            "name: missing or empty. Give the project a non-empty name."
        )
    project_type = record.get("project_type")
    if project_type not in PROJECT_TYPES:
        raise RegistryValidationError(
            "project_type: %r is not a known project type. Known types are: %s."
            % (project_type, ", ".join(PROJECT_TYPES))
        )
    environment = record.get("environment")
    if environment not in ENVIRONMENTS:
        raise RegistryValidationError(
            "environment: %r is not valid. Use one of: %s."
            % (environment, ", ".join(ENVIRONMENTS))
        )
    design_location = validate_design_location(record.get("design_location"))
    board = record.get("requirements_board")
    if not isinstance(board, str) or not board.strip():
        raise RegistryValidationError(
            "requirements_board: missing or empty. Provide the issue-tracker "
            "board key or URL, e.g. 'GOV-123' or https://tracker.example.com/board/GOV."
        )
    application_url = validate_application_url(record.get("application_url"), environment)
    features = validate_features(record.get("features"))
    mfa_exception = validate_mfa_exception(environment, features, record.get("mfa_exception"))
    return {
        "name": name.strip(),
        "project_type": project_type,
        "environment": environment,
        "design_location": design_location,
        "design_adapter": detect_design_adapter(design_location),
        "requirements_board": board.strip(),
        "application_url": application_url,
        "features": features,
        "mfa_exception": mfa_exception,
    }
