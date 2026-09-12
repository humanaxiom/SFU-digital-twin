# Codex takeover execution evidence

Started: 2026-09-10; continued 2026-09-11. Status: local takeover changes implemented;
clean local gates, browser smoke and scoped independent reviews passed;
external acceptance pending, not a repository-wide approval.

Subsequent user clarification verified all three ECC/AQ/Strand source GDBs in local
`data/`. It also exposed a gap in the earlier capability claim: the repository bind
made raw inputs accessible through `/workspace/data`, despite the absence of an
explicit source mount. The scoped Compose repair masks that path and selects the
byte-identical local legacy GDB for source-etl. Source inventory, regressions and
fresh-container boundary evidence are in [local source verification](LOCAL-SOURCE-REVIEW.md).
The full-suite totals below predate that mount repair; they have not been rerun or
represented as fresh post-repair full-suite certification.

## Baseline and preservation

Started at HEAD `998c477` with 14 modified tracked files, the existing takeover plan,
DT-015 route evidence and demo evidence module untracked. Those edits were preserved.
No commit, reset, stash, push, publication or source/artifact promotion was performed.

## Changes

- Shared AGENTS.md and thin Copilot adapter; reconciled current status, spatial rules,
  DOD and SDLC. Post-tool source hook explicitly described as diagnostic.
- Pinned published image; reconciled obsolete capability tests and extraction error
  tests that incorrectly depended on source access.
- Added make fast/gates and source-independent PR validation. Source QA now has a
  real read-only layer-count check and a required mount preflight.
- Fixed malformed HTTP profiles, admission before thread creation and idle socket
  timeout. Fixed profile changes and route cancellation during delayed room inspection.
- Added real HTTP/socket regressions and executed JavaScript state tests. These
  are not a substitute for browser DOM/layout and second-device acceptance.

## Image and artifacts

Successful GitHub Actions publication run: `34501691967`, commit
`7b92a8c7e17dc95da2d798b8abd5c94aec8c689a`.
Published digest recorded from its push log:
`sha256:26259879732ceffe8405f22d19c423bf14408583e1a752da35a61d3e2825276c`.
Registry inspection from this machine returned HTTP 403; execution with that image
is not certified here. Existing artifact container used:
`sfudt-wayfinding-dt015-18090-artifact-1`, image ID
`sha256:0b67be1d851168d326c422762b369d1ce129a9ed3c20429d5014c98ed10a4947`.

SHA-256 of accepted artifacts:

| Artifact | SHA-256 |
| --- | --- |
| wayfinding.gpkg | f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65 |
| graph_contracted.pkl | ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d |
| graph_contracted_stats.json | 2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1 |

## Fresh checks

Commands below ran inside the existing local build container with
`PYTHONPATH=/workspace/packages/wayfinding/src`, unless otherwise stated.

- RED HTTP tests reproduced unhashable profiles and socket admission/idle failures.
  A test-fixture error in an additional release test was corrected before GREEN.
- RED JavaScript test reproduced failure to recompute on profile change.
- Focused HTTP/infrastructure GREEN: 50 passed, 2 skipped.
- Client/extraction/HTTP checks: 41 passed, 12 skips for unavailable source in artifact container.
- `sh tools/check-fast.sh`: 52 passed, 2 skipped; lint, types and launcher fixture checks passed.
- Fresh offline Compose artifact container (`docker-compose.local.yml` override):
  `sh tools/check-fast.sh`: 53 passed, 2 skipped; lint, types and launcher checks passed.
  New network-isolation regression was observed RED before setting `network_mode: none`.
- `pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov -q`:
  23 passed, 1 skipped, 410 deselected, exit 0.
- Source container: `pytest packages/wayfinding/tests/test_source_dataqa.py --no-cov -q`:
  1 passed, exit 0. Seven layer counts match the accepted source profile; this is
  not an exhaustive source schema/geometry certification.
- Fresh offline source-ETL container with mount preflight and `-m source_dataqa`:
  1 passed, 435 deselected, exit 0.
- Full suite: **419 passed, 15 skipped** in 546.62 seconds. No test failures;
  pytest exited 1 because coverage was initially **82.77%**, below 85%.
- Added a real synthetic FileGDB round-trip test: 1 passed. Verifies attributes,
  CRS/dimensions, coordinates, overwrite refusal and repeat extraction without private data.
- Final fast gate rerun in a fresh offline local-image container: **54 passed,
  2 skipped**; Ruff, Pyright and launcher checks passed, exit 0. Compose configuration
  and `git diff --check` passed as well.
- Added a generator-replay test comparing freshly generated DT-015 evidence from
  accepted artifacts against the checked-in report. The previous tests only read the report.
- Supplemental runs used `--cov-append` on the full-run coverage database.
  Synthetic extraction increased coverage to 83.52%; evidence replay plus final
  infrastructure/source selection produced **27 passed, 1 skipped, exit 0**, with
  combined coverage **85.38%** (2,148 statements, 314 missed). The floor remains 85%.
  Production code was unchanged between the full and supplemental runs. This is
  full-plus-supplemental evidence, not a second clean full-suite invocation.
- Raw local outputs: `build/takeover-tests.log`, `build/takeover-tests.xml`,
  `build/takeover-coverage.log`, `build/takeover-final-coverage.log` and fast/QA logs.
  These are intentionally ignored. `tools/capture-takeover-evidence.ps1` records
  current revision, dirty-file identities and artifact hashes in `build/takeover-state.json`.

## Docker-only follow-up

Docker-only follow-up (2026-09-11): replaced host evidence processing with a thin
Git/Docker launcher and containerized Python processor. Path validation, hashing and
JSON output run in Docker; eight fixture tests cover content and path/output escapes.
The post-tool diagnostic now uses Docker directly; 32 fixture tests cover lexical
Windows/POSIX paths, malformed payloads and unassessable shell-only input. It does not
inspect the actual source or claim write prevention, shell parsing, or symlink safety.
Legacy schema/domain PowerShell parsers refuse host execution.

RED/GREEN was observed in Docker for both ports. The evidence launcher passed with
`-LocalImage`. Expanded fast gate in a fresh offline local-image artifact container:
**94 passed, 2 skipped**, Ruff/Pyright/launcher and no-host-Python checks passed,
exit 0. The two new Python tools passed Ruff separately. Raw log:
`build/docker-only-fast.log`. These results do not certify actual Copilot hook-runner
integration, published-image access, or the remaining product acceptance below.

## Resumed independent review — 2026-09-11

Parallel workers ran the established gates and retried the immutable-image pull;
a large-model reviewer independently inspected the product changes. The pull again
returned HTTP 403. The cached `2026-09-01` image has digest
`sha256:7292a160a284e1ff3dfb344a74058347aef16adb3e332697f479312d372329d4`,
which differs from the Compose pin and does not substitute for it.

The review reproduced three client problems: late scene responses could replace the
selected floor, clearing a manual destination could discard the retained origin on
the next click, and exact mobility chat could leave a default route visible. The
fixes guard scene generations and clear/synchronize route state at the common command.
Invalid or identical endpoints clear old geometry and retain elevator-only disclosure.

Actual HTTP probes also found arbitrary unmatched paths in access logs and missing
shared security headers/logging on 429 responses. Logs now use allowlisted route
templates (including an unmatched sentinel) and standard method names; 429 responses
use the common header/logging path. New regression tests first produced **6 failed,
9 passed**, including all four new client state assertions; after implementation
the focused HTTP/client/DT-015 checks passed **30 tests**. One source-regex assertion
requiring a particular conditional spelling was superseded by executed behavior.

The report's omission of a same-level Strand fixture contradicted the existing plan.
Read-only GIS review found `SH1001C` → `SH1003`: default profile, **21.829742844839366 m**,
12 measured pathway edges and geometries on Strand 1000, with distinct eligible
anchors. The added fixture failed its missing-fixture check first, then was generated
by `python -m wayfinding.demo.evidence` in Docker. Generator replay and focused
HTTP/client evidence checks passed **18 tests**. The three AQ fixtures were retained;
no graph, source or accepted build artifact changed.

A real browser startup also exposed the default `socketserver` traceback logger
when a health client disconnected during startup. A forced handler-error regression
failed before the sanitized `handle_error` override, then the HTTP/client/static set
passed **27 tests**. Unexpected failures now produce only a generic diagnostic.

### Browser evidence on the final runtime

`WAYFINDING_BROWSER_BUILD_IMAGE=wayfinding-build:local` with
`docker compose -p sfudt-takeover-browser-final -f infra/docker-compose.browser.yml up --force-recreate --abort-on-container-exit --exit-code-from browser`
exited **0**. The fresh demo used read-only code/artifact mounts; Chromium and demo
shared an internal Docker network without host ports or package installation.
Only this temporary project was removed afterward.

The pinned browser image ran **Chromium 130.0.6723.31 / Node v20.18.0**. All four
canonical fixtures passed at **1440×1000** and **390×844**; checks compare resolved
endpoints, reachability semantics, distance, edges, returned SVG geometry, steps,
warnings and provenance. Direct and mobility-chat responses match, with one route
POST and no duplicate assistant POST. Actual SVG pointer and Enter/Space events,
cross-floor final-step navigation, manual incomplete-pair correction, exact
`409 no_elevator_only_route` disclosure, and delayed scene rejection passed.
The final browser run recorded **27 API reads and 14 POSTs**, with no uncaught page errors.

Panel separation and horizontal control bounds passed. Final evidence captures
painted map, controls and room-list viewports separately to avoid stale offscreen
scroll surfaces in Chromium's full-page capture. DOM assertions independently match
both map and room list to the returned scene. Floor/route rendering and readable
controls/disclosures were inspected. This is a headless Chromium smoke check with viewport emulation,
not physical mobile-device, other-engine, screen-reader or LAN certification.
`build/takeover-browser/results.json` is the authoritative run status; its referenced
screenshots belong to that run. Earlier worker-draft results/failed files are superseded.
The expanded fixture report self-hash is
`8582890e54b7a3083f95084afca4c1214e553596d7630dccf45dcf67f85ae044`.

### Full-run isolation

An initial resumed full run overlapped the in-flight fixes: **459 passed, 16 skipped,
3 failed; 84.94% coverage**. It had imported old assertions before reading the new
four-fixture report and client source, so it is mixed-state evidence. Its log is
`build/takeover-resume-gates/full-pytest.log`. A subsequent run was stopped when the
browser exposed the traceback issue. Neither is final certification; the final
run starts after the production/test freeze and uses a fresh, separate coverage database.

Final clean local-image suite: **468 passed, 16 skipped, 0 failed in 571.93 seconds**;
coverage **87.50%** (2,160 statements, 270 missed), exit **0**, without `--cov-append`
or changing the 85% floor. Runtime image identity remains
`sha256:0b67be1d851168d326c422762b369d1ce129a9ed3c20429d5014c98ed10a4947`.
Logs, JUnit and the isolated `.coverage` database live in
`build/takeover-resume-gates/final/`.

The runner used `docker run --rm --network none`, the repository bound at `/workspace`,
working directory `/workspace`, `PYTHONPATH=/workspace/packages/wayfinding/src` and
`COVERAGE_FILE=/workspace/build/takeover-resume-gates/final/.coverage`. Exact pytest invocation:

```sh
pytest --basetemp /tmp/takeover-pytest-final --cache-clear --junitxml=/workspace/build/takeover-resume-gates/final/full-junit.xml packages/wayfinding/tests
```

Direct Docker invocation replaces only the Compose wrapper for isolated local-image
verification; pytest configuration and Makefile gate commands remain unchanged.

Skips: 2 Docker CLI checks unavailable inside the gate container, 12 source-GDB
checks unavailable in the artifact capability, 1 factual absence of an eligible
profile-isolated same-anchor pair, and 1 explicit source-QA check requiring source-etl.
These skips do not represent fresh source-QA certification.

`pyright packages/wayfinding/src` passed (0 errors/warnings). Artifact QA using
`pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov` passed
**23 tests, 1 skipped, 460 deselected** in 19.73 seconds. Both
`sh tests/gate/test_launch_stack.sh` and `sh tests/gate/test_no_host_python.sh` passed.
All ran with external networking disabled. Launcher tests use fixtures; their
"Destroyed Compose project" output does not describe teardown of existing demo stacks.

The first Ruff pass found one 102-character line in `evidence.py`. The sole
post-full-suite source edit wrapped that line. Docker-run AST comparison confirmed
identical Python semantics; then
`ruff check packages/wayfinding tools/capture_takeover_evidence.py tools/hooks/check_read_only_boundary.py`
passed, exit **0** (`lint-final.log`/`lint-final.exit`). Earlier failing lint logs
are retained. The suite was not repeated for this formatting-only edit.

## Remaining acceptance

Published-image pull and full-gate execution with that exact image; CI push/activation
and required branch check; physical
second-device machine-name LAN acceptance. The complete isolated ETL rebuild and
artifact promotion workflow remains future work; `make etl` is still a no-op.
No claim of completion is made from a historical judge verdict.
The earlier computer-use attempt reported `No browser is available`; the later
Docker-only Chromium gate above supplies the browser evidence now available.
