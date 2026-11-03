"""Input handling: structured requirements, document parsing, and the
missing-information checklist. The board never infers missing fields.
"""

import re
from typing import List, Tuple

from .models import REQUIRED_FIELDS, Requirement


def check_missing(requirement: Requirement) -> List[str]:
    """Return checklist entries for every critical field left blank."""
    missing = []
    for fname, why in REQUIRED_FIELDS:
        val = getattr(requirement, fname)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(f"{fname}: {why}")
    return missing


def parse_document(text: str) -> Tuple[Requirement, List[str]]:
    """Extract what can be extracted from free text; report the rest.

    Returns (requirement, extraction_notes). Fields not found stay None and
    will appear on the missing-information checklist.
    """
    found = {}
    notes = []
    low = text.lower()

    m = re.search(r"(\d[\d,]*)\s*(req/s|rps|requests?\s*per\s*second|events?\s*per\s*second|events/s)", low)
    if m:
        found["throughput"] = f"{m.group(1)} {m.group(2)}"
        notes.append(f"throughput <- '{m.group(0)}'")

    m = re.search(r"p\d{2}\s*(<|under|below)\s*\d+\s*ms", low)
    if m:
        found["latency_budget"] = m.group(0)
        notes.append(f"latency_budget <- '{m.group(0)}'")
    if "latency_budget" not in found:
        m = re.search(r"(\d+)\s*ms\s*(latency|response)", low)
        if m:
            found["latency_budget"] = m.group(1)
            notes.append(f"latency_budget <- '{m.group(0)}'")

    if re.search(r"\bpii\b|personal data|cardholder", low):
        found["data_sensitivity"] = "PII in scope"
        notes.append("data_sensitivity <- PII mention detected")

    m = re.search(r"\b(hipaa|pci\s*dss|soc\s*2|gdpr|iso\s*27001)\b", low)
    if m:
        found["compliance"] = m.group(1).upper()
        notes.append(f"compliance <- '{m.group(0)}'")

    m = re.search(r"team of (\d+)|(\d+)\s+engineers", low)
    if m:
        found["team_size"] = f"{m.group(1) or m.group(2)} engineers"
        notes.append(f"team_size <- '{m.group(0)}'")

    if re.search(r"cost-sensitive|tight budget|limited budget", low):
        found["budget_posture"] = "cost-sensitive"
        notes.append("budget_posture <- cost-sensitive phrasing detected")
    elif re.search(r"budget is not|generous budget", low):
        found["budget_posture"] = "budget-flexible"
        notes.append("budget_posture <- budget-flexible phrasing detected")

    m = re.search(r"\b(cloud|on-prem(?:ises)?|hybrid|multi-cloud|edge)\b", low)
    if m:
        found["deployment_target"] = m.group(1)
        notes.append(f"deployment_target <- '{m.group(0)}'")

    m = re.search(r"99\.9\d*\s*%", text)
    if m:
        found["availability_target"] = m.group(0).strip()
        notes.append(f"availability_target <- '{m.group(0)}'")

    title = text.strip().splitlines()[0][:80] if text.strip() else "Untitled requirement"
    req = Requirement(title=title, problem=text.strip()[:500], **found)
    return req, notes
