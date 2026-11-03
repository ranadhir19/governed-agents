"""Quickstart: register one project, check completeness, emit a handoff contract."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.design_registry import (
    Registry,
    build_handoff_contract,
    completeness,
)

STORE = "/tmp/design_registry_quickstart.json"
if os.path.exists(STORE):
    os.remove(STORE)

registry = Registry(STORE)
record = registry.save({
    "name": "quickstart-demo",
    "project_type": "governance-console",
    "environment": "dev",
    "design_location": "https://design-tool.example.com/file/quickstart01",
    "requirements_board": "GOV-42",
    "application_url": "http://localhost:8080/",
    "features": ["reporting", "monitoring"],
})

comp = completeness(record)
print("saved:", record["name"], "| adapter:", record["design_adapter"])
print("completeness: %.1f%% (%d/%d)" % (comp["percent"], comp["configured"], comp["total"]))
for item in comp["missing"]:
    print("  missing:", item)

contract = build_handoff_contract(
    record,
    variables=["color.primary"],
    frames=["home"],
    tokens={"color.primary": "#1b4fd8"},
    route="none",
)
print("handoff contract:")
print(json.dumps(contract, indent=2, sort_keys=True))
print("OK")
