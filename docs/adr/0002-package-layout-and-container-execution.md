# 2. Package layout and container execution model

Status: accepted
Date: 2026-08-29

## Context

DT-001 (harness bootstrap) requires establishing the package structure, test/lint/type toolchain,
and containerized execution model before any product code can be written. The decision must balance:

1. **Package granularity.** The reference `dtwin-harness` repository splits into `dtwin_core`,
   `dtwin_etl`, and `dtwin_api` packages from day one. That split was driven by a mature codebase
   with established API boundaries and separate deployment concerns. This project has zero product
   code today; premature package fragmentation introduces coordination cost (cross-package imports,
   dependency version conflicts, redundant pyproject.toml maintenance) with no offsetting benefit
   until API boundaries actually exist.

2. **Coverage enforcement.** `.github/copilot-instructions.md` prime directive 4 mandates TDD; a
   coverage floor enforces it mechanically. A single blended coverage number (e.g. 85% across all
   packages) can mask untested packages; per-package floors provide clearer accountability and allow
   different thresholds where justified (e.g. GDAL-binding adapter code vs pure routing logic).

3. **Container base image.** The existing `tools/run_profile.ps1` script uses
   `ghcr.io/osgeo/gdal:alpine-small-latest` for one specific task: OGR profiling of the source
   GDB. That image is ~800 MB and includes GDAL, PROJ, and numerous geospatial libraries.
   DT-001 Step 2 (package skeleton) and Step 4 (Makefile gates) produce no ETL code — the initial
   smoke test just imports an empty `wayfinding` module. Pulling a GDAL-heavy image for a test
   suite that doesn't touch geodata yet adds minutes of pull time and complexity. The reference
   `dtwin-harness` repository initially used a plain Python test image and later split into
   `test` (Python-only) and `test-gdal` services when GDAL-dependent code arrived; applying that
   pattern from the start defers image bloat until Phase 1 ETL work actually needs it (per
   [docs/plans/DT-001.md Step 3](../plans/DT-001.md#step-3-docker-compose-service-implementer)).

4. **Source GDB boundary.** `.github/copilot-instructions.md` prime directive 1 mandates the source
   geodatabase at `C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb` is read-only.
   Every container service that accesses it must mount it `:ro` to enforce this mechanically, not
   just by convention. Docker Desktop on Windows requires forward-slash path syntax
   (`C:/repos/...`) for bind-mount sources; backslash form (`C:\repos\...`) silently fails or
   mounts an empty directory.

## Decision

### Package layout convention

All Python packages live under `packages/<name>/` with the following structure:

```
packages/<name>/
  pyproject.toml          # Project metadata, dependencies, tool config
  src/<name>/             # Package source (enables editable installs without polluting sys.path)
    __init__.py
  tests/                  # Tests for this package (pytest discovery)
    test_*.py
```

The first package is `packages/wayfinding`. It will house ETL, core (graph construction, geodata
models), routing, and API modules as **submodules** (`wayfinding.etl`, `wayfinding.core`,
`wayfinding.routing`, `wayfinding.api`) rather than separate top-level packages. This is an explicit
deviation from the `dtwin-harness` reference, justified by the absence of any product code today:
package boundaries are cheap to add later when API contracts stabilize, expensive to retrofit into a
monolith, but even more expensive to maintain prematurely when no API exists to isolate. We will
revisit this in a future ADR when the routing engine and API are implemented and a genuine
deployment or versioning boundary emerges.

### Coverage floor policy

Coverage floors are set **per-package**, not blended across the workspace. Each `packages/<name>/`
defines its floor in its own `pyproject.toml` `[tool.pytest.ini_options]` section or in the
Makefile `test` target via `pytest --cov=packages/<name>/src --cov-fail-under=<N>`.

Initial floor for `packages/wayfinding`: **85% line coverage**, matching the `dtwin-harness`
reference and enforcing TDD from the start (per `.github/copilot-instructions.md` prime directive
4). This floor is provisional: once `packages/wayfinding` accumulates ETL code that interfaces with
GDAL/OGR bindings, genuinely hard-to-test paths (e.g. gdal.OpenEx error branches that require
corrupting a GDB on disk) may justify a `pytest.mark.skip(reason="gdal")` pattern or a lower floor
for the `wayfinding.etl` submodule specifically. That decision is deferred to the Phase 1 ETL
ticket; it is not needed for the bootstrap skeleton in DT-001.

### Tool choices

- **Linting and formatting:** `ruff`. Fast, zero-config for standard Python style, replaces both
  `flake8` and `black`.
- **Type checking:** `pyright`. Pylance (the VS Code Python language server) is built on Pyright,
  making it first-class in this environment. The workspace has Pylance-specific skills available
  (`python-fact-grounded-coding`, `pylance-refactoring`, `pylance-docs`, `pylance-python-profiling`
  per the session context), and `pyright` integrates natively with those workflows. Prefer `pyright`
  over `mypy` unless a future dependency requires `mypy`-specific plugins.
- **Testing:** `pytest` + `pytest-cov`. Industry standard; `pytest-cov` provides per-package
  coverage enforcement via `--cov-fail-under`.

### Container execution model

A single `infra/docker-compose.yml` defines all services. For DT-001 (bootstrap), one service
suffices:

```yaml
services:
  test:
    image: python:3.12-slim
    working_dir: /workspace
    volumes:
      - ./packages/wayfinding:/workspace/packages/wayfinding:rw
      - C:/repos/sfudt/claude/dtwin-harness/data/IndoorWayfinding.gdb:/data/IndoorWayfinding.gdb:ro
    command: /bin/sh
```

The base image is `python:3.12-slim` (NOT `ghcr.io/osgeo/gdal:alpine-small-latest`) because DT-001
produces no ETL code that reads geodata. The GDAL-capable image will be added in Phase 1 when ETL
implementation begins, following the `dtwin-harness` reference's split into `test` (Python-only) and
`test-gdal` services. This defers ~800 MB of image bloat and minutes of pull time until it is
actually required.

All `Makefile` gate targets (`make test`, `make lint`, `make type`) wrap
`docker compose -f infra/docker-compose.yml run --rm test <command>`. No Python, pip, or GDAL is
invoked on the host — this enforces
`.github/instructions/container-only-execution.instructions.md` mechanically.

### Source GDB mount

The geodatabase at `C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb` is mounted
**read-only** in every service that needs it, at a fixed in-container path:

```
C:/repos/sfudt/claude/dtwin-harness/data/IndoorWayfinding.gdb:/data/IndoorWayfinding.gdb:ro
```

Note the **forward-slash source path** (`C:/repos/...`): Docker Desktop on Windows requires this
form for bind mounts. Backslash paths (`C:\repos\...`) are not portable to docker-compose.yml YAML
syntax and may silently fail. The `:ro` suffix is mandatory (enforces
`.github/copilot-instructions.md` prime directive 1: write boundary). Any container that attempts to
write to `/data/IndoorWayfinding.gdb` will fail with a read-only filesystem error.

## Consequences

### Positive

- **Single package reduces early-stage friction.** No cross-package imports, no
  intra-monorepo dependency resolution, no redundant pyproject.toml files. Code moves from
  `wayfinding.core.graph` to a hypothetical future `wayfinding_core.graph` package via a
  refactoring ticket when the API boundary justifies it, not before.
- **Per-package coverage floors prevent masking.** A 90% overall number can hide a 40% package.
  Explicit per-package floors make accountability clear.
- **Lightweight test image accelerates iteration.** The `python:3.12-slim` image (~150 MB) pulls in
  seconds; the GDAL image (~800 MB) is deferred until Phase 1 ETL work requires it.
- **Toolchain is Pylance-native.** `pyright` integrates with existing VS Code skills and language
  server; no impedance mismatch with `mypy`.
- **Read-only mount is mechanically enforced.** A stray `ogr.Open(..., update=True)` call will fail
  immediately, not silently corrupt the source.

### Negative

- **Package split is deferred, not avoided.** When the API and routing engine reach production
  maturity, a future ADR will split `packages/wayfinding` into `packages/wayfinding_core`,
  `packages/wayfinding_api`, etc. That refactoring has a cost (cross-package imports, version
  pinning); we accept it because the cost of premature splitting is higher (coordination overhead
  with no isolating benefit).
- **Coverage floor may need revision.** 85% is achievable for pure Python routing logic but may be
  too high for GDAL-binding adapter code (hard-to-test error paths). A future ADR may introduce a
  `not gdal` marker or lower the floor for `wayfinding.etl` specifically; that complexity is
  deferred until ETL code exists.
- **Windows path convention is Docker Desktop-specific.** The `C:/repos/...` forward-slash form
  works on Windows with Docker Desktop but may differ on Linux (where `/mnt/c/repos/...` is typical
  under WSL) or macOS. Document this explicitly in bootstrap instructions; revisit in Phase 4+ CI
  configuration if the repo needs to run on Linux build agents.

### Supersedes

None. This is the first package-layout decision.

### Independent of

ADR-0001 (record architecture decisions). This ADR follows the format established there but does not
modify it.

### Will require revision when

1. The routing engine and API reach production maturity and a genuine deployment boundary exists
   (e.g. the API is deployed as a separate service with independent versioning). At that point,
   split `packages/wayfinding` into `packages/wayfinding_core` (graph, geodata models),
   `packages/wayfinding_etl` (GDB → GeoPackage pipeline), and `packages/wayfinding_api` (FastAPI
   service). Document that decision in a new ADR superseding this one.

2. Phase 1 ETL work begins and GDAL/OGR bindings are added as dependencies. At that point, extend
   `infra/docker-compose.yml` with a `test-gdal` service using
   `ghcr.io/osgeo/gdal:alpine-small-latest`, and split `make test` into `make test-unit` (pure
   Python, `test` service) and `make test-integration` (geodata I/O, `test-gdal` service). That
   change does not require a new ADR — it is a mechanical extension of this one's container model.

3. The 85% coverage floor proves too high for ETL code with genuinely hard-to-test GDAL error
   branches. At that point, either add `pytest.mark.skip("gdal")` or lower the floor for
   `wayfinding.etl` specifically, documented in a one-paragraph addendum to this ADR (not a new ADR
   unless the policy change affects other packages).
