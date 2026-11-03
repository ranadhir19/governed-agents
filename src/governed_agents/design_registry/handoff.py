"""The design-handoff contract: no single route required.

A JSON contract (variables, frames/components, tokens) that works
whether the design tool's API, its MCP server, or neither is reachable.
Each capability documents which route it needs.
"""

CONTRACT_VERSION = "1.0"

# Capability -> routes that can provide it. "none" means the contract
# itself (or a previously exported file) is sufficient: no live route.
ROUTE_CAPABILITIES = {
    "extract_design_variables": ["api", "mcp"],
    "list_frames": ["api", "mcp"],
    "list_components": ["api", "mcp"],
    "read_style_tokens": ["api", "mcp", "none"],
    "consume_contract_offline": ["none"],
    "diff_contract_versions": ["none"],
    "push_review_annotations": ["api"],
    "subscribe_to_design_changes": ["api", "mcp"],
}


def capability_routes():
    """Document which route each handoff capability needs."""
    return {cap: list(routes) for cap, routes in ROUTE_CAPABILITIES.items()}


def build_handoff_contract(record, variables=None, frames=None, tokens=None,
                           route="none", notes=None):
    """Build the JSON-serializable handoff contract for a project record.

    route is the route the contract content was sourced from:
    'api', 'mcp', or 'none' (hand-authored / previously exported).
    """
    if route not in ("api", "mcp", "none"):
        raise ValueError(
            "route: %r is not valid. Use one of: api, mcp, none." % (route,)
        )
    contract = {
        "contract_version": CONTRACT_VERSION,
        "project": record.get("name"),
        "project_type": record.get("project_type"),
        "environment": record.get("environment"),
        "design_location": record.get("design_location"),
        "design_adapter": record.get("design_adapter", "unknown"),
        "sourced_via_route": route,
        "variables": list(variables or []),
        "frames": list(frames or []),
        "tokens": dict(tokens or {}),
        "capability_routes": capability_routes(),
        "notes": notes or "",
    }
    return contract
