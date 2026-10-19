# 06 — Design Registry

## Problem

Every governed delivery project has the same coordinates: its designs (in a
design tool), its requirements (in an issue tracker), the environment it runs
in, and the URL people open. These coordinates live in people's heads and
chat messages. Handoffs fail because a recommendation was never tested where
the work happens: nobody can answer "where is the design, what are the
requirements, where does it run, what URL do people open" from one place.

## Solution

One registry, one answer. Each project has a single record — design file
location (link or file key), requirements board, environment, application URL,
feature set — stored as a plain JSON file plus validation. No database; the
value is one answer instead of several.

- **Fixed vocabulary.** Project types (`ai-assistant-rollout`, `use-case-intake`,
  `governance-console`, `twin-configuration`, `core-governance`) and features
  (`reporting`, `multi-factor-auth`, `project-launch`, `monitoring`) are fixed
  lists; environments are only `dev` and `production`. No project invents its
  own terms.
- **Validation that refuses bad saves** with actionable messages: the design
  location must be a valid design-tool link or file key (Figma is one supported
  adapter among generic concepts — file link or file key — detected from the
  link host); URLs must be http(s); unknown features are rejected. Production
  gets strict checks: a production entry must give the application URL, and
  production without multi-factor-auth needs a deliberate recorded exception
  (`mfa_exception` with reason and approver), never a silent default.
- **Completeness, not just presence.** Each project reports % configured and
  exactly what is missing. A corrupt store never crashes the reader (graceful
  degradation); features added to the vocabulary later appear on existing
  records automatically (schema evolution).
- **Reachability measured, not assumed.** A network probe tests the endpoints a
  design handoff depends on — reachability only, never credentials — and
  reports per-endpoint reachable/blocked with evidence (e.g. a TLS handshake
  reset suggests a proxy that is not allow-listed; a refused connection means
  the host is up but the port is closed).
- **A handoff that depends on no single route.** A JSON design-handoff
  contract (variables, frames/components, tokens) works whether the design
  tool's API, its MCP server, or neither is reachable; each capability
  documents which route it needs.

## Architecture

```
src/governed_agents/design_registry/
  vocabulary.py    fixed PROJECT_TYPES / FEATURES / ENVIRONMENTS
  validation.py    RegistryValidationError; actionable per-field rules,
                   production strictness, MFA exception requirement
  registry.py      JSON-file store; graceful corrupt-read; schema evolution;
                   bad saves refused before any write
  completeness.py  % configured + exact missing-item list per project
  probe.py         TCP/TLS reachability probe, per-endpoint evidence,
                   no credentials ever sent
  handoff.py       design-handoff contract + capability->route documentation

06-design-registry/
  demo.py          seeded end-to-end run (see below)
  results/         results.md, handoff_contract.json
  tests/           17 smoke tests
```

## How to run

```
cd ~/workspace/governed-agents
python3 06-design-registry/demo.py        # full end-to-end demo
python3 06-design-registry/tests/test_smoke.py   # 17/17 smoke tests
python3 examples/06_design_registry_demo.py      # quickstart
```

## Results

From the seeded demo run (`python3 06-design-registry/demo.py`):

- **Registration:** 2 of 3 projects saved (`assistant-rollout-dev`,
  `twin-config-prod`). The third (`governance-console-prod`) was **refused**
  with an actionable message: production entries must give the application
  URL. The refused save was never written to the store.
- **Completeness:** `assistant-rollout-dev` 77.8% (7/9) — missing
  `multi-factor-auth` and `project-launch`; `twin-config-prod` 81.8% (9/11) —
  same two features missing.
- **Corrupt store:** after overwriting the JSON file with garbage, the reader
  reported `store_corrupt=True`, returned 0 records, and did not crash; the
  registry remained writable and recovered on the next save.
- **Probes:** local open port reachable (tcp_connect_succeeded, ~2-5 ms);
  closed localhost port blocked (connection_refused); TLS handshake against a
  connection-dropping server blocked with `tls_handshake_failed` evidence
  distinguishing it from a refused connection.
- **Handoff contract:** emitted to `results/handoff_contract.json`
  (`contract_version` 1.0, variables/frames/tokens, `sourced_via_route: none`).

See `results/results.md` for the full measured record.
