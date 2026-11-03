"""Completeness: percent configured plus exactly what is missing."""

from .vocabulary import FEATURES


def completeness(record):
    """Return configured/total percent and the list of missing items."""
    missing = []
    configured = 0
    total = 0

    def check(label, present):
        nonlocal configured, total
        total += 1
        if present:
            configured += 1
        else:
            missing.append(label)

    check("name", bool(record.get("name")))
    check("project_type", bool(record.get("project_type")))
    check("design_location", bool(record.get("design_location")))
    check("requirements_board", bool(record.get("requirements_board")))
    check("environment", bool(record.get("environment")))
    if record.get("environment") == "production":
        check("application_url (required for production)",
              bool(record.get("application_url")))
    # dev: application_url is optional, not counted either way.
    features = record.get("features", {})
    for name in FEATURES:
        check("feature '%s' enabled" % name, bool(features.get(name)))
    if (record.get("environment") == "production"
            and not features.get("multi-factor-auth")):
        check("mfa_exception (production without multi-factor-auth)",
              bool(record.get("mfa_exception")))

    percent = round(100.0 * configured / total, 1) if total else 0.0
    return {
        "percent": percent,
        "configured": configured,
        "total": total,
        "missing": missing,
    }
