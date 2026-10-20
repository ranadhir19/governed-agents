# Validation

Run the uniform harness from the repo root:

```bash
python3 validate.py
```

It is deterministic and offline, prints PASS/FAIL per stage, and exits 0
only when the final line reads `HARNESS GREEN`. Any failure exits non-zero
with `HARNESS RED: <stages>`.

## Stages and what they cover

1. **Import / compile** - parses `pyproject.toml`, byte-compiles every
   `.py` file in the repo (75 files), and imports the `governed_agents`
   package plus every submodule (56 modules: the top-level package and its
   6 system subpackages) with `PYTHONPATH=src`.
2. **Full test suite** - runs the complete existing pytest suite over the
   whole repo in a subprocess. The per-system suites all share the
   basename `tests/test_smoke.py`, so pytest is invoked with
   `--import-mode=importlib`; under the default import mode collection
   fails with "import file mismatch" before a single test runs. Importlib
   mode runs every test file - nothing is skipped, renamed, or weakened.
   Current result: **83 passed**.
3. **Forbidden-reference scan** - scans the whole tree with the standing
   external scanner kept outside this repository (an embedded copy of the
   same patterns is the fallback). Every candidate is judged in context:
   the harness's own pattern definitions, and literals inside the
   banned-term guard tests (`test_no_forbidden_names` / `BANNED` lists in
   three systems' smoke tests), are benign meta-references - they exist
   precisely to assert the banned terms are absent everywhere else, and
   removing them would weaken the tests. Anything else that matches is a
   real reference and fails the stage; the harness never auto-removes
   such content, because whether it may be changed is the owner's
   decision. Current result: 18 candidates (13 in `validate.py` itself,
   5 in guard tests), **0 real references**.
4. **Results / docs consistency (existence only)** - every relative
   markdown link in every README resolves; every `results/...` and
   `experiments/...` file a README names exists; each of the 6 system
   folders ships an entry point (`demo.py`), `tests/test_smoke.py`, and
   `results/results.md`.

## What this harness does NOT cover

- It does **not** re-run the demos or experiments, and does not
  re-verify the measured numbers in `results/results.md` files against
  fresh runs. Regeneration is the demos' job; results files are checked
  for existence only, never for numeric correctness.
- It does not validate the *content* of READMEs (claims, headline
  numbers, prose) - only that referenced files exist.
- The pytest suites are the systems' own smoke tests, authored alongside
  the code. Passing them shows the code behaves as its authors asserted;
  it is not an independent domain-coverage audit, and no claim is made
  that uncovered behaviour is correct.
- The forbidden-reference scan judges candidates by the two documented
  meta-reference rules and fails closed on anything else. A novel
  benign context would fail the stage until a human judges it and, if
  appropriate, extends the rules with the justification recorded.
- No network, installation-from-PyPI, or packaging/release checks are
  performed; the package is exercised from the source tree only.
