"""End-to-end demo of the design registry (seeded, deterministic).

1. Register 3 projects; one invalid save is refused with an actionable message.
2. Show completeness % and exactly what is missing per project.
3. Corrupt the store file and show the reader degrading gracefully.
4. Probe 3 example endpoints and report reachable/blocked with evidence.
5. Emit a JSON design-handoff contract.
"""

import json
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from governed_agents.design_registry import (
    Registry,
    RegistryValidationError,
    build_handoff_contract,
    completeness,
    probe_endpoint,
    probe_endpoints,
)

STORE = os.path.join(os.path.dirname(__file__), "results", "demo_store.json")
CONTRACT_OUT = os.path.join(os.path.dirname(__file__), "results", "handoff_contract.json")

PROJECTS = [
    {
        "name": "assistant-rollout-dev",
        "project_type": "ai-assistant-rollout",
        "environment": "dev",
        "design_location": "https://design-tool.example.com/file/AbC123xYz",
        "requirements_board": "GOV-101",
        "application_url": "http://localhost:3000/",
        "features": ["reporting", "monitoring"],
    },
    {
        # Invalid: production entry without the application URL.
        "name": "governance-console-prod",
        "project_type": "governance-console",
        "environment": "production",
        "design_location": "designfilekey-9f8e7d6c5b4a",
        "requirements_board": "https://tracker.example.com/board/GOV",
        "features": ["reporting", "multi-factor-auth", "project-launch", "monitoring"],
    },
    {
        "name": "twin-config-prod",
        "project_type": "twin-configuration",
        "environment": "production",
        "design_location": "https://www.figma.com/file/QwErTy0987",
        "requirements_board": "GOV-202",
        "application_url": "https://twin.example.com/",
        "features": {"reporting": True, "monitoring": True},
        "mfa_exception": {
            "reason": "service account only, no interactive login; network allow-list in place",
            "approved_by": "platform lead",
            "expires": "2027-01-31",
        },
    },
]


def main():
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    if os.path.exists(STORE):
        os.remove(STORE)
    registry = Registry(STORE)

    print("== 1. registering projects ==")
    for project in PROJECTS:
        try:
            saved = registry.save(project)
            print("saved: %-24s adapter=%s" % (saved["name"], saved["design_adapter"]))
        except RegistryValidationError as exc:
            print("REFUSED: %s\n  -> %s" % (project["name"], exc))

    print("\n== 2. completeness ==")
    for record in registry.list():
        comp = completeness(record)
        print("%s: %.1f%% configured (%d/%d)" % (
            record["name"], comp["percent"], comp["configured"], comp["total"]))
        for item in comp["missing"]:
            print("    missing: %s" % item)

    print("\n== 3. corrupt store, graceful read ==")
    with open(STORE, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json !!!")
    recovered = Registry(STORE)
    print("store_corrupt=%s records=%d (reader did not crash)"
          % (recovered.store_corrupt, len(recovered)))
    print("corrupt_error: %s" % recovered.corrupt_error)

    print("\n== 4. endpoint probes (reachability only, no credentials) ==")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    open_port = listener.getsockname()[1]
    listener2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener2.bind(("127.0.0.1", 0))
    closed_port = listener2.getsockname()[1]
    listener2.close()
    endpoints = [
        "127.0.0.1:%d" % open_port,
        "127.0.0.1:%d" % closed_port,
    ]
    for result in probe_endpoints(endpoints, timeout=2.0):
        print("%-28s %-9s %s" % (
            result["endpoint"], result["status"], result["evidence"]))
        if result["latency_ms"] is not None:
            print("%-28s           latency_ms=%s" % ("", result["latency_ms"]))
    # TLS handshake against a server that accepts then immediately drops the
    # connection: the handshake is reset/rejected, classified separately
    # from a refused connection.
    import threading
    rejector = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rejector.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rejector.bind(("127.0.0.1", 0))
    rejector.listen(1)
    reject_port = rejector.getsockname()[1]

    def _reject_once():
        try:
            conn, _ = rejector.accept()
            conn.close()
        except OSError:
            pass

    thread = threading.Thread(target=_reject_once, daemon=True)
    thread.start()
    tls_result = probe_endpoint("127.0.0.1:%d" % reject_port, timeout=2.0, tls=True)
    thread.join(timeout=3.0)
    rejector.close()
    print("%-28s %-9s %s" % (
        tls_result["endpoint"] + " (tls)",
        tls_result["status"], tls_result["evidence"]))
    listener.close()

    print("\n== 5. design-handoff contract ==")
    record = registry.get("twin-config-prod")
    contract = build_handoff_contract(
        record,
        variables=["color.primary", "spacing.base"],
        frames=["login", "dashboard", "review-queue"],
        tokens={"color.primary": "#1b4fd8", "spacing.base": "8px"},
        route="none",
        notes="Exported without a live design-tool route; consumable offline.",
    )
    with open(CONTRACT_OUT, "w", encoding="utf-8") as fh:
        json.dump(contract, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps(contract, indent=2, sort_keys=True)[:600] + "\n...")
    print("contract written to %s" % CONTRACT_OUT)
    print("\nDONE")


if __name__ == "__main__":
    main()
