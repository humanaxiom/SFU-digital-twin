# DT-024 follow-up — visible rooms and compact navigation

Date: 2026-09-19 (America/Vancouver). Based on merged PR #4, `617fe1b`.
Branch: `feat/dt-024-clickable-map`. Status: locally verified; not committed or published.

## Problem and delivered scope

Building selection previously stopped at a footprint, with floor buttons below
the campus map. The floor room list lived in collapsed record details. Mobile
stacked navigation, map tools and forms vertically, requiring substantial page
scrolling. All eleven real floor scenes contain rooms (3–263 each); there is no
missing-room data repair in this change.

Persistent primary building and exact-ID floor buttons now sit above the map.
Building buttons, search results and clickable footprints open the remembered or
default recorded floor directly. Secondary dropdowns remain in More navigation
options. Room buttons and a floor-local filter are visible beside/below the map.
The compact toolbar and collapsed secondary forms reduce initial page length;
route instructions appear when a route exists. Original stale-response guards
and route geometry contracts remain in force.

The follow-up also closes the screenshot-reported directions defects. Start
choices are scoped to the floor being viewed; after a start is selected, the
destination dropdown contains mapped connections only instead of more than one
thousand unrelated rooms. The later compactness correction removes
the duplicate scrollable “Directions to…” list, leaving one destination control.
Clicking a route journey floor now
selects that visit's first instruction, so map, instruction and step position
advance together.

This follow-up delivers the journey-entry synchronization item from Stage D. The
larger endpoint draft/commit state-machine change remains pending. This does not
change API, source artifacts, graph topology, route safety or connectivity. Room
selection still uses the existing endpoint interaction until Stage C.

## RED and independent review

The first browser run confirmed missing primary building/floor controls. Its
hidden-map zero-height observation was not accepted as layout evidence. Corrected
baseline `build/navigation-review/baseline-compact-20260917d/` records a 390px
map top of 417.6px, hidden room list, and the actual eleven-floor catalog. The
existing baseline and failure records remain preserved.

Large-model architecture/legacy checks use `gpt-6-astra`; the bounded new browser
harness uses `gpt-5.6-luna`. A separate large-model judge reviews the final combined
diff and evidence. The lead integrates production and documentation.

The final independent review found two native-select edge cases and one visibility
regression: explicit unsupported/assistant endpoints could disappear from scoped
selects, and no-step route failures could hide their map-adjacent explanation. Both
were fixed and covered. Browser diagnosis also found redundant availability requests
and mapped-option replacement during guidance floor changes; route-following now
preserves the catalog and does not requery it.

## Validation

All project execution below runs in Docker. This section records final local evidence.

- Final task browser check:
  `build/navigation-review/crossfloor-final4/compact-navigation-results.json`,
  exit 0. It exercised all 3 buildings/11 floors, typed room filtering, built a
  real AQ 2000 → AQ 5000 route through visible room buttons, selected the next
  route visit and verified its map and first instruction together. It verified
  mapped-only destination choices and desktop/390px/320px layout without clipping.

- Duplicate-list removal E2E:
  `build/navigation-review/no-duplicate-mapped-list-e2e-final/compact-navigation-results.json`,
  exit 0. The exact live client has no duplicate mapped-route action list, retains
  one mapped destination selector, completes the real cross-floor route and passes
  all-buildings/all-floors plus 320px/390px/desktop checks.
- Post-removal full suite: **631 passed, 16 skipped**, **86.25% coverage**,
  261.72 seconds, exit 0; `build/navigation-review/no-duplicate-mapped-list-full-test.log`.
  Ruff and Pyright passed with no findings; artifact data QA passed **23**, skipped
  **1**, with 623 deselected.

- Final canonical browser check:
  `build/takeover-browser/crossfloor-canonical-final16/results.json`, exit 0. Both
  1440x1000 and 390x844 passed all four canonical fixtures, route/API parity,
  cross-floor instruction selection, Swap, disconnected visible-room requests,
  delayed-response guards, pointer/keyboard interaction and layout checks.

- Final full suite: **631 passed, 16 skipped**, **86.25% coverage**, 256.58 seconds,
  exit 0; `build/navigation-review/crossfloor-final5-full-test.log`.
- Final Ruff and Pyright: exit 0, no findings. Artifact data QA: **23 passed,
  1 skipped, 623 deselected** in 9.86 seconds, exit 0.

- Fresh full suite: **631 passed, 16 skipped**, **86.25% coverage**, 281.90 seconds,
  exit 0; `build/navigation-review/compact-final2-full-test.log`. The final CSS
  scrollbar-width correction landed during this run. A subsequent final client/static
  invocation passed **37 tests**, 610 deselected, 1.62 seconds, exit 0. This is
  full-suite plus final focused evidence; fresh browser runs cover assembled CSS.
  Skips: 2 unavailable Docker-CLI checks, 12 source-GDB checks, 1 source-QA check
  requiring the source-etl mount, and 1 accepted-artifact profile-isolated-pair case.
- Integrated client/static regressions: **22 passed** in 1.40 seconds, exit 0.
  Files: `test_dt024_navigation.py`, `test_dt023_client.py`,
  `test_dt013_static_client.py`, `test_takeover_client.py`, `test_dt018_client.py`.
  The route-state mock DOM was extended with `dataset`, attributes and event
  handlers so it can represent the new native navigation buttons.
- All client/static tests: **37 passed**, 610 deselected, 1.71 seconds, exit 0.
  Command: the artifact Docker pytest invocation with `-k "client or static" --no-cov -q -o cache_dir=/tmp/compact-allclient-cache`.
- The first full suite returned **630 passed, 16 skipped, 1 failed**, 86.25% coverage
  in 277.61 seconds. The only failure required an obsolete `h2#route-heading`
  instead of the new `summary#route-heading`. That assertion now checks the actual
  summary while preserving every disclosure assertion. Its focused file passed
  **9 tests** in 0.16 seconds. The first log remains
  `build/navigation-review/compact-final-full-test.log`; a fresh full rerun uses
  `compact-final2-full-test.log`, `/tmp/compact-final2-coverage` and `/tmp/compact-full2-cache`.
- Phase B navigation browser: **5 checks passed**, no failures, completed
  `2026-09-18T03:48:57.083Z`. All 11 floors, explicit Open floor, native ArrowDown,
  late route/Return, and retained-scene failure/Retry passed. Evidence:
  `build/navigation-review/compact-phaseb-final3/navigation-results.json` and
  desktop/mobile screenshots.
- Ruff: exit 0, all checks passed. Pyright: exit 0, no errors or warnings.
- Artifact data QA: **23 passed, 1 skipped**, 623 deselected, 9.98 seconds, exit 0.
  The skip is the accepted-artifact case without an eligible profile-isolated pair.
- Launcher, no-host-Python and rebuild-launcher checks: all exit 0. Direct shell
  invocation first failed on inherited CRLF line endings. As in the preceding
  phase report, Docker Python copied `tools/`, `infra/`, `tests/gate/`, and
  `Makefile` into a temporary directory and normalized only those copies to LF.
  Repository scripts are unchanged. Log:
  `build/navigation-review/compact-final-launchers.log`.
- Local host-port health via Docker curl: exit 0, routing enabled and all three
  artifact hashes agree with the checks below.

Established Makefile-equivalent gate commands use the running artifact container:

```text
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests/test_dt024_navigation.py packages/wayfinding/tests/test_dt023_client.py packages/wayfinding/tests/test_dt013_static_client.py packages/wayfinding/tests/test_takeover_client.py packages/wayfinding/tests/test_dt018_client.py --no-cov -q -o cache_dir=/tmp/compact-focused-cache
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 sh -lc 'exec env PYTHONPATH=/workspace/packages/wayfinding/src COVERAGE_FILE=/tmp/compact-final-coverage pytest packages/wayfinding/tests -o cache_dir=/tmp/compact-full-cache > build/navigation-review/compact-final-full-test.log 2>&1'
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src ruff check packages/wayfinding
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src pyright packages/wayfinding/src
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov -o cache_dir=/tmp/compact-dataqa-cache
```

Legacy browser checks now assert that building/footprint activation requests a
floor scene without requesting a route, with the latest exact floor winning
asynchronous races. Floor navigation uses real primary button clicks. Optional
native dropdown/Open-floor checks explicitly open More navigation options.
The existing building search check explicitly opens Building names and search.
The first canonical `compact-final` run failed because the migrated race fixture
clicked an already displayed singleton ECC floor, so no new request was available
to hold. The fixture now requests a different AQ floor from ECC. This was a test
migration correction, not a production failure.
Subsequent canonical attempts found two further test-boundary issues: an
immediate redundant floor click while the newly entered scene changed layout,
and nonpainted dropdown boxes inside closed details being counted as visible
overflow. Sequential selection now waits for its actual scene; layout checks use
`checkVisibility()`, with a separate explicit summary-open test validating the
expanded dropdown bounds. The superseded pre-final-CSS `compact-final5` run was
stopped to reduce scene API contention. The final CSS corrects a separate real
320px scrollbar-width clipping issue; final browser labels are `compact-final6`
and `compact-phaseb-final3`.
Canonical6 completed all four desktop fixtures and interaction/layout checks,
then its mobile repeat exposed one final migrated assertion: building entry may
reuse the already displayed exact floor without a scene request. The assertion
now requires zero requests only for that exact reuse, otherwise one, and still
forbids route requests. A complete rerun is required after that harness correction.

Canonical route fixtures: AQ2035.2 → AQ5046 (elevator only), AQ5029 → AQ5044
(default), AQ1010 → AQ2103 (default), SH1001C → SH1003 (default). Checks preserve
exact recorded API geometry, per-floor route overlays, assistant parity,
pointer/keyboard room selection, available/limited guidance and failure outcomes.

Runtime uses the supported **local image override**, not the published immutable
Compose image. This validation does not certify publication or physical LAN access.

- Local image: `sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`.
- Demo container: `a75cd93b32a524b404a61eca7da99c46222c10ecc4185822eef964d0a35bc292`.
- Artifact container: `5f338a0781d62c22601fec45a29b65f827ea3b94a522b2658130b15126fe2612`.
- Browser image: `mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`.
- Browser API target: `http://127.0.0.1:8080` in the existing demo network namespace.
- User-facing local URL: `http://127.0.0.1:18007/`.

Docker `sha256sum` confirms unchanged accepted artifacts:

| Artifact | SHA-256 |
| --- | --- |
| GeoPackage | `f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65` |
| Graph | `ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d` |
| Stats | `2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1` |

No source/build change requires a source-to-candidate rerun for this UI increment.
No artifact promotion or new topology/accessibility claim is made.

Final canonical browser command (isolated evidence label):

```text
docker run --rm --init --shm-size=1gb --network container:sfudt-wayfinding-18000-demo-1 --workdir /workspace --mount type=bind,source=C:/repos/sfudt/ghcp/packages/wayfinding,target=/workspace/packages/wayfinding,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/tests/browser,target=/workspace/tests/browser,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/docs/reports/DT-015-demo-routes.json,target=/workspace/docs/reports/DT-015-demo-routes.json,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/wayfinding.gpkg,target=/workspace/build/wayfinding.gpkg,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/graph_contracted.pkl,target=/workspace/build/graph_contracted.pkl,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/graph_contracted_stats.json,target=/workspace/build/graph_contracted_stats.json,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/takeover-browser,target=/workspace/build/takeover-browser --env WAYFINDING_BROWSER_BASE_URL=http://127.0.0.1:8080 --env WAYFINDING_BROWSER_RUN_LABEL=compact-final6 mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db node /workspace/tests/browser/demo.cjs
```

Phase B navigation command:

```text
docker run --rm --init --shm-size=1gb --network container:sfudt-wayfinding-18000-demo-1 --workdir /workspace --mount type=bind,source=C:/repos/sfudt/ghcp/tests/browser,target=/workspace/tests/browser,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/docs/reports/DT-015-demo-routes.json,target=/workspace/docs/reports/DT-015-demo-routes.json,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/navigation-review,target=/workspace/build/navigation-review --env WAYFINDING_BROWSER_BASE_URL=http://127.0.0.1:8080 --env WAYFINDING_BROWSER_RUN_LABEL=compact-phaseb-final3 mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db node /workspace/tests/browser/navigation.cjs
```
