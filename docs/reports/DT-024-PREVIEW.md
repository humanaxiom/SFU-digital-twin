# DT-024 — Explicit route preview, 2026-11-20

The [Stage C plan](../plans/DT-024.md) and [ADR-0017](../adr/0017-navigation-state-and-journey.md)
define separate identities for the editable draft, submitted request and
displayed route. Room search, native menus, Swap, assistant directions and
explicit room actions edit the draft. Preview submits the selected snapshot.
Clear cancels pending previews and keeps the inspected room, floor and camera.
This increment uses the existing deterministic service and trusted artifacts.

## Regressions reproduced

Docker Chromium reproduced an immediate route POST when selecting SH1036 →
SH3050.1, before Preview. See `build/navigation-review/dt024-preview-red/results.json`.
The Node state harness also recorded three unintended requests after edits and
Swap, and one after an assistant direction request. Both tests failed (exit 1,
container `ba1403b46d48`).

During review, two more tests failed in `d8c3a0ae13f7`. Editing the draft could
release an earlier pending availability check before its network result arrived.
A malformed HTTP 200 could also replace the displayed identity. Preview now
retains the submitted pair's availability promise and checks response identity
and the guidance structure used by the renderer before committing. Valid
limited or unavailable guidance replaces the prior route with its own evidence.

A delayed inspection of a second room exposed its endpoint buttons alongside
the first room's facts (RED `8cec47a6a0ae`). Selecting a room now immediately
shows its identity, updates the map highlight and opens the inspector. A failed
detail lookup leaves the selected identity with an unavailable message. Late
details cannot move keyboard focus away from a later action.

## Verification environment

Git HEAD `5ca5186329e5dcf9df28a4f512280d7fc6c2d299` with inherited local
work. Package checks used `infra/docker-compose.yml` plus the local override,
`PYTHONPATH=/workspace/packages/wayfinding/src` and build image
`sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`.
The browser used pinned Chromium image
`mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`.
Canonical tests used the accepted artifacts. The other isolated demos mounted
the three `sh-navigation-exact-20260923` artifacts read-only. No source build,
promotion, public TLS probe, registry or physical LAN test was part of this
client increment.

```sh
pytest packages/wayfinding/tests -q -rs
ruff check packages/wayfinding
pyright packages/wayfinding/src
pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov -rs
sh tests/gate/test_launch_stack.sh
sh tests/gate/test_rebuild_launcher.sh
sh tests/gate/test_no_host_python.sh
```

The combined navigation, campus, static, takeover, availability, guidance and
profile disclosure suite passed 55 tests in `8581bebb7c09`. Ruff (`42478d1776bf`), Pyright (`c58de8fb4a8b`), stack launcher
(`daed407ea0ce`), rebuild launcher and no-host-Python checks (`bf002cecfbfc`)
exited 0. Artifact QA exited 0 in `02449aef3c50` with 23 passes, one expected
skip for the artifact-specific isolated same-anchor case and 654 deselections.

## Final browser and HTTP checks

The committed summary initially took on the replacement request’s pending and
error styling. Chromium reproduced this in `dt024-preview-summary-red` (exit 1).
The summary now keeps its successful state while the separate request status
announces pending or failure. The final pointer and keyboard replay checked
both the summary text and its computed background, alongside the route geometry.

The isolated demo `84d59b992aa5` served 1,017 rooms across three buildings and
11 levels. SH1036 ↔ SH3050.1 returned 90.697610 m each way, 50 graph edges,
396 guidance coordinates and visits to Strand floors 1000, 2000 and 3000. A
real elevator-only request returned HTTP 409 `no_elevator_only_route`. An injected
HTTP 503 on the availability endpoint exercised the manual fallback and the actual failed
replacement. Other checks delayed the real result through Swap or Clear, verified
assistant drafts and room actions, and covered pointer, keyboard and 320 px.

| Probe | Recorded result | SHA-256 of results.json |
| --- | --- | --- |
| Preview workflow | 11 checks, 4 desktop and 2 mobile route POSTs, `dt024-preview-stage-c-delivery`, browser `10730a59b865` | `8630eb8225f1b81ab0e4039fcb6ebcf74f479d229e6318af14347728c39725de` |
| N05 room search | 15 checks, 3 real HTTP 200 route requests and direct HTTP 409, `dt024-preview-search-stage-c-delivery`, browser `42e5481080fd` | `8050cbf40afe90c80ab3046a3b15f6cf3e8d8502681eb2e5fd7d6baa98403416` |

These JSON files and screenshots are under `build/navigation-review/<label>/`.
Docker verified the following served files.

| File | SHA-256 |
| --- | --- |
| app.js | `87d34d343b9108b8566f9f4dce795ee21ccbbf210b0f8aef0846edfb1bc822c8` |
| index.html | `42ee122e6eb06256d05b991e150b95eeaaf1756e57e980f5c9c1e4c2bb0d1882` |
| styles.css | `0bf5beed10e52ca2271d7b374217de1081c63fe0805f7e53c130dd36073124c3` |
| Candidate GeoPackage | `da44fc5683169c53efcc0b2080cea4419ff40833dad8fb47c8b76051ec656eac` |
| Candidate graph | `93c2ff2994e6e564adecae3506175f2c0047948e1d84e44045d2c70267071d46` |
| Candidate stats | `9a678cb044f6c76d3abf61bfa57a0e56fafb00efb0d181f5a7906492b23a6cfb` |

For the workflow probes, set `WAYFINDING_CANDIDATE_RUN=sh-navigation-exact-20260923`,
`WAYFINDING_BROWSER_BUILD_IMAGE=wayfinding-build:local` and an unused loopback
`WAYFINDING_CANDIDATE_PORT` (18147 for this run). Start the private Compose demo
and attach the pinned browser to its candidate network. Mount `tests/browser`
read-only and `build/navigation-review` writable at their corresponding
`/workspace/` paths. Set the result label and `WAYFINDING_BROWSER_BASE_URL=http://demo:8080`
and run `node tests/browser/preview-route.cjs` or `node tests/browser/room-search.cjs`.
Both final serial runs exited 0. Removing the project and its networks exited 0.

The initial full suite recorded 661 passes, 16 skips and one stale assertion
that changing the draft profile immediately hides the displayed route’s
elevator-only disclosure. The revised test checks that the committed profile
owns that disclosure. A runtime assertion exercises the transition from a
committed elevator-only route to a stairs-capable draft. Older automatic-route
fixtures were also migrated to the explicit Preview and inspection actions.

Final full Docker suite exited 0 in `543255042e41` (`dt024-replay-full`),
with **662 passed, 16 expected skips and 86.96% coverage** in 429.07 s.
Twelve extraction checks and one dedicated source QA check require the mounted
raw source. One test each requires Docker CLI, GNU Make, or the profile-specific
same-anchor fixture absent from the accepted artifact. The complete command was
`docker compose -p dt024-replay-full -f infra/docker-compose.yml -f infra/docker-compose.local.yml run --rm artifact sh -c 'hostname; exec env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -q -rs'`.

## Supporting browser regressions

The migrated suites check that rooms remain inspectable even when a route is
unavailable. Map and dropdown selections only submit on Preview. Late route
results preserve newer floor navigation, and replacing a draft does not allow
stale availability responses to choose a different endpoint. A development run
issued several suites concurrently against one local demo; competing scene loads
exceeded the test timeout. The final navigation probes ran serially on the same
candidate (`144176e69c89`, Compose project `sfudt-preview-reg`) and exited 0.
The probe directories below are under `build/navigation-review`.

| Probe directory | Checks | Result SHA-256 |
| --- | ---: | --- |
| dt024-preview-crossfloor-room-picking-checked | 12 | `8a581be0fc4e30ae53134eaafbaee600c258f924bfdb2f8cb97139e80877ded7` |
| dt024-preview-navigation-checked | 5 | `a2e486e55fe6262e58247cbbb63608369b0e67ceb118648f8940102aa9cece7b` |
| dt024-preview-sh-crossfloor-checked | 5 | `35b835677a78001528601adcd13e3b235fd1cb9ba374cc88332feb94989a14ca` |
| dt024-preview-compact-navigation-checked | 6 | `30b62c9a9066085dcabb1a0404f9df1bb3b8d12df659115b17696ef74abd7086` |

Run the corresponding `tests/browser/<probe>.cjs` entry point with the same
Docker mounts and variables as above. `navigation.cjs` additionally reads the
read-only fixture `docs/reports/DT-015-demo-routes.json`. The isolated project
was removed after verification (exit 0).

The canonical accepted-artifact suite also exited 0. It replayed AQ2035.2 →
AQ5046 (elevator only), AQ5029 → AQ5044, AQ1010 → AQ2103 and SH1001C → SH1003,
including recorded geometry, mobile/desktop controls, assistant parity, an
unsupported HTTP route and delayed responses. It recorded 279 GETs and 33 POSTs.
`build/takeover-browser/dt024-preview-verified/results.json` has SHA-256
`75fecf92fc227b2bec1c63a307aebeb61a75208b9afec6fa4dbbf4a1c6c4ecd2`.
The demo was `40d4c53d07de`, browser `624bac6a0068`. Accepted GeoPackage, graph
and stats hashes matched the DT-033 protected artifact record. Compose down
removed the canonical project after the browser completed.

```powershell
$env:WAYFINDING_BROWSER_BUILD_IMAGE='wayfinding-build:local'
$env:WAYFINDING_BROWSER_RUN_LABEL='dt024-preview-verified'
docker compose -p sfudt-preview-final -f infra/docker-compose.browser.yml up --force-recreate --abort-on-container-exit --exit-code-from browser
```

The historical candidate browser entry point `candidate.cjs` was exercised with
the retained Strand candidate and a Docker-generated fixture in its original
format. It compared both route outcomes, 1,016 availability entries per profile,
exact SVG geometry, selected instructions and camera fit at desktop/mobile
widths. Default exposed 309 connected destinations (historical endpoint-only
baseline 7), elevator-only 64. The browser recorded 94 reads and 7 POSTs and
exited 0. `build/takeover-browser/dt024-legacy-candidate-final1/results.json`
has SHA-256 `dee96f6a40c9843eb2524862411f1f79732d0dceec359b27bc80012056e71956`.
Its input is retained in `dt024-legacy-candidate-input/fixture.json` under the
same parent directory, SHA-256 `78139f7547851e684878bfef7260e698fa76db3288010511a904bc6c98602f69`.
This compatibility check used DT-025 evidence. The historical DT-022 topology
experiment was outside the client increment.

Independent `gpt-6-astra` review accepted the scoped Stage C client delivery
after inspecting the final runtime, regressions, browser evidence and screenshots.
There were no blocking findings. Stage D journey and mobile work is tracked
separately in the plan.
