"""Smoke tests for the design registry (stdlib only)."""

import json
import os
import socket
import sys
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from governed_agents.design_registry import (
    Registry,
    RegistryValidationError,
    build_handoff_contract,
    capability_routes,
    completeness,
    probe_endpoint,
)
from governed_agents.design_registry.validation import validate_project


def _tmp_store():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return path


def _valid_dev():
    return {
        "name": "proj-dev",
        "project_type": "use-case-intake",
        "environment": "dev",
        "design_location": "https://design-tool.example.com/file/abc123",
        "requirements_board": "GOV-1",
        "features": ["reporting"],
    }


def test_rejects_unknown_project_type():
    rec = _valid_dev()
    rec["project_type"] = "moon-base"
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        assert "moon-base" in str(exc) and "ai-assistant-rollout" in str(exc)
        return
    raise AssertionError("unknown project_type was accepted")


def test_rejects_bad_design_location_actionable():
    rec = _valid_dev()
    rec["design_location"] = "notaurl"
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        msg = str(exc)
        assert "design_location" in msg and "http" in msg and "file key" in msg
        return
    raise AssertionError("bad design_location was accepted")


def test_rejects_unknown_feature():
    rec = _valid_dev()
    rec["features"] = ["teleportation"]
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        assert "teleportation" in str(exc) and "reporting" in str(exc)
        return
    raise AssertionError("unknown feature was accepted")


def test_rejects_non_http_url():
    rec = _valid_dev()
    rec["application_url"] = "ftp://files.example.com/app"
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        assert "application_url" in str(exc)
        return
    raise AssertionError("non-http URL was accepted")


def test_production_requires_application_url():
    rec = _valid_dev()
    rec["environment"] = "production"
    rec["features"] = ["multi-factor-auth"]
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        assert "production" in str(exc) and "application_url" in str(exc)
        return
    raise AssertionError("production without URL was accepted")


def test_production_mfa_requires_recorded_exception():
    rec = _valid_dev()
    rec["environment"] = "production"
    rec["application_url"] = "https://app.example.com/"
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        assert "mfa_exception" in str(exc)
        return
    raise AssertionError("production without MFA and without exception was accepted")


def test_production_mfa_exception_incomplete_refused():
    rec = _valid_dev()
    rec["environment"] = "production"
    rec["application_url"] = "https://app.example.com/"
    rec["mfa_exception"] = {"reason": "no interactive login"}
    try:
        validate_project(rec)
    except RegistryValidationError as exc:
        assert "approved_by" in str(exc)
        return
    raise AssertionError("incomplete mfa_exception was accepted")


def test_production_mfa_exception_accepted():
    rec = _valid_dev()
    rec["environment"] = "production"
    rec["application_url"] = "https://app.example.com/"
    rec["mfa_exception"] = {"reason": "service account", "approved_by": "lead"}
    saved = validate_project(rec)
    assert saved["mfa_exception"]["approved_by"] == "lead"


def test_bad_save_not_written():
    path = _tmp_store()
    registry = Registry(path)
    registry.save(_valid_dev())
    bad = _valid_dev()
    bad["name"] = "proj-bad"
    bad["design_location"] = "bogus"
    try:
        registry.save(bad)
    except RegistryValidationError:
        pass
    assert registry.get("proj-bad") is None
    assert len(registry) == 1
    with open(path, encoding="utf-8") as fh:
        stored = json.load(fh)
    assert [p["name"] for p in stored["projects"]] == ["proj-dev"]
    os.remove(path)


def test_corrupt_store_graceful_and_recoverable():
    path = _tmp_store()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("definitely not json {{{")
    registry = Registry(path)
    assert registry.store_corrupt is True
    assert len(registry) == 0
    assert registry.corrupt_error
    # The registry remains writable after a corrupt read.
    registry.save(_valid_dev())
    assert len(registry) == 1
    assert registry.store_corrupt is False
    os.remove(path)


def test_schema_evolution_adds_new_features():
    path = _tmp_store()
    legacy = {
        "version": 1,
        "projects": [
            {
                "name": "legacy",
                "project_type": "core-governance",
                "environment": "dev",
                "design_location": "legacyfilekey1234",
                "requirements_board": "GOV-9",
                "features": {"reporting": True},
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(legacy, fh)
    registry = Registry(path)
    record = registry.get("legacy")
    assert record is not None
    # Features added to the vocabulary later appear on old records.
    assert set(record["features"]) == {
        "reporting", "multi-factor-auth", "project-launch", "monitoring",
    }
    assert record["features"]["reporting"] is True
    assert record["features"]["monitoring"] is False
    os.remove(path)


def test_completeness_percent_and_missing():
    record = validate_project(_valid_dev())
    comp = completeness(record)
    assert comp["total"] == 9
    assert comp["configured"] == 6
    assert comp["percent"] == 66.7
    assert "feature 'multi-factor-auth' enabled" in comp["missing"]
    assert "feature 'project-launch' enabled" in comp["missing"]
    assert "feature 'monitoring' enabled" in comp["missing"]
    assert len(comp["missing"]) == 3


def _local_server(reject=False):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    if reject:
        def _run():
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                pass
        threading.Thread(target=_run, daemon=True).start()
    return srv, port


def test_probe_reachable_and_refused():
    srv, open_port = _local_server()
    closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()
    ok_result = probe_endpoint("127.0.0.1:%d" % open_port, timeout=2.0)
    assert ok_result["status"] == "reachable"
    assert "tcp_connect_succeeded" in ok_result["evidence"]
    assert ok_result["latency_ms"] is not None
    refused = probe_endpoint("127.0.0.1:%d" % closed_port, timeout=2.0)
    assert refused["status"] == "blocked"
    assert "connection_refused" in refused["evidence"]
    srv.close()


def test_probe_tls_handshake_classified():
    srv, port = _local_server(reject=True)
    result = probe_endpoint("127.0.0.1:%d" % port, timeout=2.0, tls=True)
    assert result["status"] == "blocked"
    assert "tls_handshake_failed" in result["evidence"]
    srv.close()


def test_probe_dns_failure_classified():
    real_getaddrinfo = socket.getaddrinfo

    def _fail(*args, **kwargs):
        raise socket.gaierror(8, "Name or service not known")

    socket.getaddrinfo = _fail
    try:
        result = probe_endpoint("does-not-exist.example:443", timeout=2.0)
    finally:
        socket.getaddrinfo = real_getaddrinfo
    assert result["status"] == "blocked"
    assert "dns_resolution_failed" in result["evidence"]
    assert "unreachable" in result["evidence"]


def test_handoff_contract_routes_documented():
    routes = capability_routes()
    assert routes["consume_contract_offline"] == ["none"]
    assert routes["push_review_annotations"] == ["api"]
    assert set(routes["extract_design_variables"]) == {"api", "mcp"}
    contract = build_handoff_contract(validate_project(_valid_dev()), route="none")
    assert contract["contract_version"] == "1.0"
    assert contract["sourced_via_route"] == "none"
    json.dumps(contract)  # must be JSON-serializable


def test_handoff_rejects_bad_route():
    try:
        build_handoff_contract(validate_project(_valid_dev()), route="carrier-pigeon")
    except ValueError as exc:
        assert "api, mcp, none" in str(exc)
        return
    raise AssertionError("bad route was accepted")


TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    failures = 0
    for test in TESTS:
        try:
            test()
            print("PASS %s" % test.__name__)
        except Exception as exc:
            failures += 1
            print("FAIL %s: %r" % (test.__name__, exc))
    print("%d/%d passed" % (len(TESTS) - failures, len(TESTS)))
    sys.exit(1 if failures else 0)
