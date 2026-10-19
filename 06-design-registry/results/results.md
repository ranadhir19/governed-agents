# Results — design registry (seeded demo run)

Run: `python3 06-design-registry/demo.py` (exit 0). All numbers below are
from that actual run. Probe ports vary per run (OS-assigned); outcomes are
deterministic.

## 1. Registration (3 projects, 1 refused)

| Project | Type | Env | Outcome |
|---|---|---|---|
| assistant-rollout-dev | ai-assistant-rollout | dev | saved (adapter: generic-link) |
| governance-console-prod | governance-console | production | **REFUSED** — production entry without application URL |
| twin-config-prod | twin-configuration | production | saved (adapter: figma), with recorded MFA exception |

Refusal message (verbatim):
`application_url: missing, but environment is 'production'. Production
entries must give the application URL people open (http(s) URL). Refusing
the save.`

The refused save was verified absent from the store file.

## 2. Completeness

- assistant-rollout-dev: **77.8%** (7/9). Missing: feature
  'multi-factor-auth' enabled; feature 'project-launch' enabled.
- twin-config-prod: **81.8%** (9/11). Missing: feature
  'multi-factor-auth' enabled; feature 'project-launch' enabled.
  (The recorded `mfa_exception` satisfies the production MFA rule.)

## 3. Corrupt store

After writing `{ this is not valid json !!!` over the store file:

- `store_corrupt=True`, `records=0`, reader did not crash.
- `corrupt_error`: `JSONDecodeError: Expecting property name enclosed in
  double quotes: line 1 column 3 (char 2)`.
- A subsequent `save()` succeeded and cleared the corrupt flag.

## 4. Endpoint probes (reachability only, no credentials sent)

| Endpoint | Status | Evidence |
|---|---|---|
| 127.0.0.1:(open) | reachable | tcp_connect_succeeded, latency ~2-5 ms |
| 127.0.0.1:(closed) | blocked | connection_refused: host is up but the port is closed or filtered |
| 127.0.0.1:(dropper) + TLS | blocked | tls_handshake_failed (UNEXPECTED_EOF_WHILE_READING): connection reached the host but the TLS handshake was reset or rejected. Possible TLS-intercepting proxy that is not allow-listed, or a non-TLS service on this port. |

Note: this sandbox intercepts all outbound TCP (even reserved
`.invalid` names resolve), so the demo probes loopback endpoints only.
DNS-failure classification is covered by a unit test with a stubbed
resolver (`dns_resolution_failed ... host unreachable`).

## 5. Design-handoff contract

Emitted to `results/handoff_contract.json`: `contract_version` 1.0,
project `twin-config-prod`, 2 variables, 3 frames, 2 tokens,
`sourced_via_route: "none"`, plus the capability->route map:

- needs api or mcp: extract_design_variables, list_frames,
  list_components, subscribe_to_design_changes
- api only: push_review_annotations
- api, mcp, or none: read_style_tokens
- none (contract alone suffices): consume_contract_offline,
  diff_contract_versions

## 6. Smoke tests

`python3 06-design-registry/tests/test_smoke.py`: **17/17 passed** —
validation refusals (5), production strictness (4), bad-save suppression,
corrupt-store resilience + recovery, schema evolution, completeness math,
probe classifications (4), handoff contract + route documentation.
