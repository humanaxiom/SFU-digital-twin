# Handoff — Living Project State

## Next implementation — DT-024 navigation overhaul (2026-09-17)

User authorized updating and merging plans, documentation and architecture. [DT-024](plans/DT-024.md) and [ADR-0017](adr/0017-navigation-state-and-journey.md) now define the next implementation contract; application work has not started. Implementation requires a separate user instruction. When requested, start with Stage A regression RED evidence, then state/floor reliability. Existing legacy topology and DT-017/DT-023 data gates remain unchanged. [Documentation delivery evidence](reports/DT-024-DOCUMENTATION.md) records current verification and review. Earlier preview and verification entries below are historical, not DT-024 acceptance.

## Navigation review — overhaul proposed

The user reported broken cross-level navigation, poor dropdown choices and floor
clicking. Fresh Docker Chromium/API review reproduced a late route response
reverting a newer floor selection, a Floor choice silently changing Building, and
route floor-tab → Next returning to the old instruction's floor. All 11 scene
endpoints and four recorded routes respond; fragmentation and limited geometry
remain separate data constraints. See [navigation review and overhaul proposal](reports/NAVIGATION-REVIEW.md)
for evidence, proposed interaction/state model and staged acceptance. No product
code, route artifacts or deployment configuration changed; implementation is not
started. Prior deployment smoke success does not establish usability acceptance.


## Local deployment — 2026-09-16

Refreshed main to b7ec7b6697c6ca8d580f087503d308ef73cb60b9. Prior tracked and
untracked work is preserved in stash `pre-refresh-deploy-2026-09-16` (not reapplied).
The new AGENTS.md preservation rule arrived with this update, after that stash.

Live URL: http://127.0.0.1:18007/ (localhost only).
Compose project: `sfudt-wayfinding-18000`; artifact, source-etl and demo are healthy.
Published image pull returned unauthorized, so this deployment uses the supported
local override, built from infra/Dockerfile.build with requirements.lock.
Image: sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a.
Demo container: a75cd93b32a524b404a61eca7da99c46222c10ecc4185822eef964d0a35bc292.

Commands (exit 0 unless noted):
- `docker build -f infra/Dockerfile.build -t wayfinding-build:local .`
- Set `DTWIN_DEMO_BIND_ADDRESS=127.0.0.1`, then run `powershell -NoProfile -ExecutionPolicy Bypass -File C:\repos\sfudt\ghcp\tools\launch-stack.ps1 -ComposeFile C:\repos\sfudt\ghcp\infra\docker-compose.yml -LocalImage`.
- Docker curl probe of host.docker.internal:18007/demo/v1/health with Host localhost:18007: status ok, routing true.
- `docker exec sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests/test_dt023_campus.py packages/wayfinding/tests/test_takeover_http.py --no-cov`: 19 passed, no skips, one GDAL future warning.
- Pinned Playwright image ran tests/browser/demo.cjs in the deployed demo network namespace with WAYFINDING_BROWSER_BASE_URL=http://127.0.0.1:8080 and WAYFINDING_BROWSER_RUN_LABEL=deploy-20260916. Desktop/mobile four route fixtures, campus synchronization, guidance, parity, pointer/keyboard and layout checks passed; 320px checks passed. Evidence: build/takeover-browser/deploy-20260916/results.json and screenshots, completed 2026-09-16T17:31:08.623Z.

Artifacts unchanged; Docker sha256sum and health agree:
- GeoPackage: f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65
- Graph: ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d
- Stats: 2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1

This is a local deployment smoke verification, not a new full-suite or source
rebuild acceptance. Full gates were not rerun. No candidate artifacts promoted.
Published-image authentication and the launcher's default PSScriptRoot argument
remain unresolved; explicit ComposeFile avoids the latter. Host-port health was
verified separately from browser checks inside the deployed container namespace.
Older preview URLs and validation below are historical for this machine.


Read this first every session. Update it when the user asks, and whenever a ticket closes or a
decision is made that would leave this file materially stale — it should stay current enough that a
fresh session can resume cold from it alone.

## Current increment — building clicks synchronize dropdowns

The 2026-09-14 Building/Floor synchronization is implemented in
[PR #2](https://github.com/humanaxiom/SFU-digital-twin/pull/2), targeting `main`;
**fresh Docker verification passed**. The PR records Git integration status.
Preserve all inherited working-tree changes. ADR-0016 documents the control contract.
Clicking a footprint or choosing a building by search/list/keyboard now selects its
exact facility and valid recorded global floor order together: retain the current
order, otherwise order 0, otherwise the first recorded level. Overview-only buildings
keep their facility with an empty, disabled Floor control. Selection stays in Building
context and preserves route endpoints/profile without requesting a scene or route.
Clear/route-start cleanup no longer restores controls from a hidden old floor.

Docker actual-client and real host-port Chromium RED evidence preceded the fix.
Focused client checks passed (4 tests), followed by full gates: **617 passed,
16 skipped, 86.25% coverage**, lint, types, artifact QA and launcher/boundary checks.
Fresh candidate host-port and isolated accepted browser/API runs passed desktop,
mobile and 320 px at **14:22:10 UTC** and **14:22:08 UTC**, respectively. The full
suite subsequently passed in 935.34 seconds. Independent code/visual review found
no material blocker. See `docs/reports/DT-023.md` for commands, identities and limits.
Preview remains **http://127.0.0.1:18117/**; reload to get the mounted client.
No source, routing topology or accepted artifact changed; no promotion is implied.
The temporary accepted regression stack was removed. Full-campus inventory,
outdoor/portal GIS admission and separate DT-017 source reconciliation remain open;
this UI increment does not remove those data gates.

## Current work — DT-023 three-building overview

Branch `feature/dt-023-campus-routing` preserves the inherited planning changes.
ADR-0016 implements an explicitly incomplete AQ/ECC/Strand campus pilot with source
footprints, building search and real floor selection. The `/demo/v1/campus` response
is derived from the loaded trusted artifact; no source, accepted artifact or routing
topology changed. Fresh Docker verification passed: **617 tests, 16 expected skips,
86.25% coverage**, lint, types, artifact QA and launcher/boundary checks. Final
candidate and accepted browser/API runs passed at desktop, mobile and 320 px;
independent visual/code review found no blocker for this bounded increment.
Read `docs/reports/DT-023.md` for commands, identities, skips and remaining gates.

Use the dedicated matching backend/client preview at **http://127.0.0.1:18117/**.
Publication repair: the internal-only Docker network suppressed this container's
configured host binding. `docker network connect bridge sfudt-dt023-review` restored
the loopback port and it survived restart. When recreating this preview with the
report's Compose command, attach that bridge as well. Prior container-namespace
browser tests did not prove Windows-port reachability; see the report's follow-up.
The fresh Docker browser/API run through the published host port passed at
**04:04:19 UTC on 2026-09-12**, including all 11 candidate fixtures at desktop/mobile
and 320 px coverage (`build/takeover-browser/dt023-host-port-final/`).
Older port-18087/18107 instructions below are historical. Those backends were not
restarted and may not support the new mounted client's campus API.

Fresh Stage 0 evidence is `build/dt023-gis/audit-final3.json` and
`docs/reports/DT-023-GIS.md`: the unpromoted DT-022 candidate has 8,220 connected
AQ→ECC and 8,220 ECC→AQ room pairs in each profile, and no Strand cross-building
pairs. Every count uses authored facility/level IDs and directed reachability;
same-anchor pairs are counted separately. Revised feature 22562 touches two AQ
levels at identical XYZ, reinforcing that source coincidence cannot assign a level.

The full DT-023 ticket remains incomplete. Next data work requires authoritative
campus inventory, classification/grade of the 141 additions and verified portals;
DT-017 multipart reconciliation is still separate. No candidate promotion is implied.

## DT-023 staged scope and remaining data gates

Start with [`docs/plans/DT-023.md`](plans/DT-023.md). The requested next feature is to
show all Burnaby campus buildings and calculate routes between them. The first
three-building overview increment is underway on the branch above. Continue the
plan's staged delivery without presenting this local pilot as all-campus coverage.

Use multiple parallel agents with non-overlapping ownership. Use large models for
planning, GIS/topology analysis, architecture, orchestration and final judging; use
smaller models for bounded implementation, fixtures, documentation and routine gate
work. All project execution and data inspection remains Docker-only with `data/`
read-only. The lead must integrate, fix failures and iterate.

The decisive scope split is campus overview versus verified routing. Local indoor data
contains only AQ, ECC and Strand Hall, while SFU's public inventory lists many Burnaby
buildings. DT-022's unpromoted candidate has 8,220 reachable AQ↔ECC room pairs in both
profiles but zero Strand↔AQ/ECC pairs. The revised GDB has 141 unassigned pathways
(FIDs 22427–22567, 12,800.80 m); a large exact-source component touches AQ and Strand,
but missing facility/level/grade/access semantics make it review evidence rather than
an admissible route. Supplemental entrances, doors and ramps also lack authoritative
facility/path joins and remain excluded under ADR-0008.

The P0 GIS gate is an authoritative campus facility catalog, classification of the 141
features, a noded pedestrian network with grade/crossing semantics, and stable portals
joining each public entrance to exact indoor and outdoor endpoints. Accessibility is a
separate gate. Room Finder and Google Maps may support naming/orientation checks only;
they are not sources for route topology or accessibility.

Implement in stages: measured coverage and data contract; campus overview; verified
AQ/ECC/SH pilot; journey guidance/UI; campus expansion. Keep accepted artifacts frozen
until an isolated baseline/candidate comparison and explicit promotion decision. Do not
infer crossings, connect nearby geometry or draw centroid routes.

Standing acceptance rule: capture RED evidence, run focused checks, then fresh full
Docker gates and candidate-backed real-browser/API E2E on the final integrated revision,
including desktop, mobile and 320 px. Fix and repeat until green. Record commands,
image/artifact identities, timestamps, screenshots, skips and limitations in the
DT-023 report. No unit-only or stale-stack result is sufficient.

## Current status — DT-022 exact source-vertex topology

The AQ6071 failure was an importer defect: exact same-level endpoint-to-interior
source vertices were not connected. ADR-0015 and `docs/reports/DT-022.md` document
the opt-in correction and evidence. Final same-source runs are
`dt022-endpoint-final3` and `dt022-exact-final3`; the candidate gains 257,108
default and 230,356 elevator-only room pairs with zero losses. AQ6071 reaches 696
connected destinations instead of one. Source-slice audit and candidate-backed
browser/API E2E pass. Accepted artifacts remain unchanged and the candidate is not
promoted. Continue with the 18 audited exclusions and revised-source reconciliation
only as separately reviewed work.

## Route camera fix — DT-021, 2026-09-11

The user clarified the visible failure with AQ303 → AQ3149: routing succeeds but
initial step selection framed a single starting marker in a 16m square. DT-021
under ADR-0014 opens the current-floor route overview, supplies explicit map Zoom
in/out, retains manual camera on same-floor redraw and resets context on floor
changes. Point-only instructions use route context; coincident landing markers
fall back to the whole floor. Marker padding accounts for mobile screen space.

The real-browser RED reproduced the exact screenshot. Final live Docker browser
E2E passed at **22:28:10 UTC**, including exact-pair viewport/marker containment,
zoom/reset, express-floor context, canonical routes, mobile/320px and stale-response
checks. Full suite: **593 passed, 16 skipped, 87.03% coverage**; post-freeze client
set **27 passed**; Ruff, Pyright and artifact QA passed. See `docs/reports/DT-021.md`.
No backend or accepted artifact changed.
Reload **http://127.0.0.1:18087/** to load the mounted client changes.

## Route availability fix — DT-020, 2026-09-11

The port-18087 demo is refreshed with origin/profile-specific destination groups
under ADR-0013, visible map-adjacent failures, stale availability guards and a
native-select Swap/assistant fix. Older services returning no structured guidance
now show an update-needed message. The exact user's failing pair and URL remain
unprovided; observed recent requests returned 409 while canonical routes worked.

Fresh browser/API E2E against the actual refreshed demo passed at **22:09:05 UTC**:
desktop/mobile, four canonical fixtures, screenshot AQ route/reverse, ECC, connected
choices, native Swap both ways, unsupported selection, profile changes, delayed
availability/Clear, exact selected spans and 320px controls. Independent visual
review found no blockers. Full Docker regression: **593 passed, 16 skipped,
87.03% coverage**; Ruff, Pyright and artifact QA (**23 passed, 1 skipped**) passed.
Commands, evidence and limitations are recorded in `docs/reports/DT-020.md`.

Use **http://127.0.0.1:18087/** and reload. Other older demo stacks were not refreshed.
Accepted artifacts and route calculation remain unchanged. Most arbitrary room
pairs still lack a mapped connection; DT-017 source/geometry work remains separate.

## Latest support fix — DT-019, 2026-09-11

If `rebuild.ps1` reports a missing published image, use the existing development
image explicitly: `.\tools\rebuild.ps1 -RunId 001 -LocalImage` (unused run ID).
Launcher errors now explain this and preserve Docker diagnostics. `Build` still
uses legacy `IndoorWayfinding.gdb`; local image selection does not select revised data.
Fresh full launcher-to-candidate E2E `launcher-local-20260911` completed with source
reverification and matching artifact hashes. Launcher/boundary checks and 3 focused
infrastructure tests passed. Accepted artifacts and the running demo are unchanged.
Read `docs/reports/DT-019.md`. DT-017 remains the next data/importer task.

## Completed route UI — DT-018, 2026-09-11

The user authorized implementation after a short GIS request, now written in
`docs/requests/GIS-DATA-NEEDED.md`. DT-018 implements structured guidance and the
route UI under ADR-0012: one active floor, an ordered journey, transition phase
controls, readable directions and exact blue step highlighting. Shared local SVG
coordinates fix fragmented strokes while preserving native geometry. Final Docker
gates passed: **572 tests, 16 skipped, 86.88% coverage**; after the renderer fix,
**27 affected client/static tests** passed. Fresh browser/API E2E passed at
**2026-09-11 21:08:37 UTC**, including desktop/mobile/320px and screenshot-route/reverse/ECC
checks. Independent large-model implementation and visual review approved the local
scope. Read `docs/reports/DT-018.md` for commands, skips, evidence and limits.

The user's demo was refreshed at **http://127.0.0.1:18087/**; reload the page to get
the final client. Only that existing demo was recreated. Raw data is now masked in
its workspace mount. The temporary browser project was removed; other stacks remain
unchanged. No commit, push or source/artifact promotion was performed.

DT-017 remains separate: the screenshot's AQ1003 → AQ5053.2 route has a known
geometry/distance disagreement and therefore shows preview-only guidance with
null walking distances and generic walking text. Floor transitions remain explicit.
Canonical route fields and accepted artifacts are unchanged. GIS request was written,
not sent; no source correction or promotion is implied.

Standing user requirement: **always run fresh end-to-end tests in Docker before
declaring green**, including small or documentation-only deliveries. Assemble the
final runnable code/configuration/artifacts first; recording results afterward does
not require a redundant rerun. Follow AGENTS and DOD for scope and evidence.

## Completed DT-016 work — historical evidence

Fresh follow-up verification passed: `dt016-e2e-20260911` completed the full
source-to-candidate pipeline and matched candidate C semantically. Separately,
the real demo browser/API gate passed all four canonical fixtures at desktop/mobile
sizes on the existing accepted artifacts (2026-09-11 08:36:51 UTC). Source/build
and browser evidence are recorded in `docs/reports/DT-016.md`; no integrated
candidate-to-browser claim is made. DT-017 must exercise its corrected candidate
through the isolated demo. Published-image, CI and physical LAN acceptance remain open.

DT-016 implements executable source review and a complete isolated legacy rebuild.
Read `docs/plans/DT-016.md`, ADR-0011 and `docs/reports/DT-016.md` for the current
scope. Final clean Docker suite passed **535 tests, 16 skipped, 86.01% coverage**;
Ruff, Pyright, artifact QA (23 passed, 1 skipped), launcher and no-host-Python
checks passed. Final real-data build/review checks passed. `make etl` now invokes the isolated pipeline with
an explicit run ID; it no longer invokes the legacy no-op entry point.

Final candidates `build/experiments/dt016-legacy-c` and `dt016-legacy-d` completed
extraction, normalization, all graph stages, semantic analysis and source recheck.
Their graph/unit/anchor signatures and profile reachability match, while artifact
bytes differ. Each has 7,450 nodes, 19,884 directed edges and 1,017 eligible
approximate room anchors. Of 516,636 distinct unordered room pairs, the graph connects
33,361 by default and 29,364 with elevator-only. These are graph-level results,
not physical navigation or accessibility certification. Candidates are unpromoted.

Final source review is `build/experiments/reviews/dt016-source-review-final.json`.
All seven indoor layers preserve legacy features; revised adds 141 pathways without
facility/level IDs. Source quality remains blocked: eleven legacy/revised AQ3000
pathways also have noncontiguous stored multipart order. Independent GIS review
confirmed four accepted contracted chains retain 41 non-source join segments and
cost/geometry disagreements. Reproducing legacy semantics does not validate them.

**Next product task: DT-017**, `docs/plans/DT-017.md`. Correct multipart assembly in
isolated candidates and verify original-segment preservation and cost/geometry
consistency; then reconcile revised assignments and compare room reachability.
During DT-016, no raw source or accepted artifact was modified and no running stack
was restarted. The later DT-018 demo refresh is recorded above and in its report.
GHCR access, CI activation and physical LAN acceptance remain separate open items;
they do not prevent this local source/build work.

Commands: `./tools/rebuild.ps1 -RunId <new-id> -LocalImage`; `-Action Review` creates
a source report; `-Action Compare -RunId <left> -OtherRunId <right>` compares completed
runs. POSIX and Make equivalents are documented in README. All execution is Docker-only.

## Previous takeover status — 2026-09-11

Codex is continuing from HEAD `998c477` and the inherited dirty DT-015 working tree.
The old delivery record below is historical, not current certification.

Local-source clarification: all ECC/AQ/Strand files are present in `data/`.
Both indoor GDBs contain 3 facilities, 11 levels and 1,210 raw units. Local legacy
`IndoorWayfinding.gdb` is byte-identical to the previously selected sibling copy.
Source-etl now selects that local copy read-only. Compose masks `/workspace/data`
in artifact, source-etl and demo; the old broad workspace bind exposed raw inputs
despite earlier claims of source exclusion. Fresh-container visibility/read-only
checks pass for all three services, and local source QA passes (1 test).
Focused post-repair gates pass: 90 tests, 2 Docker-CLI skips, Ruff, launcher fixtures
and no-host-Python checks; logs are under `build/local-source-review/`.
Existing containers retain their old mounts until recreated; none was restarted.
See `docs/reports/LOCAL-SOURCE-REVIEW.md` for source hashes and exact evidence.

Revised pathways preserve the 22,426 legacy records and add 141 with null facility
and level IDs. Reconcile those and the renamed pathway layer before an isolated
rebuild. Supplemental data contains 82 entrances, 82 main doors and 34 ramps;
it remains profile-only under ADR-0008. Local availability was never the reason
for deferring revised-source promotion.

Resumed review fixed floor-response ordering, manual correction and chat pending/invalid
state; unmatched logs, 429 headers/logging and unexpected-handler traces are sanitized.
The missing Strand requirement is restored in the four-fixture report: `SH1001C` →
`SH1003`, 21.8 m over 12 measured same-level pathway edges, alongside three AQ examples.
Large-model review found no remaining blocking issue in these changes.

The Docker-only browser gate now passes on headless Chromium **130.0.6723.31** at
1440×1000 and 390×844. It checks all four canonical fixtures, exact chat parity,
returned geometry, cross-floor navigation, actual SVG pointer/Enter/Space activation,
manual correction, disconnected elevator-only disclosure and delayed scene responses.
Panel separation and horizontal control bounds passed; route screenshots were inspected.
Results/screenshots: `build/takeover-browser/`. This uses viewport emulation, not a
physical second-device LAN test. The temporary internal-network gate stack was removed;
previously running demo stacks were not changed. The last clean local-image full
suite passed **468 tests, 16 skipped, 87.50% coverage**. Ruff, Pyright, artifact QA
(**23 passed, 1 skipped**), launchers and no-host-Python checks passed. Full-run skips
are 2 unavailable Docker-CLI checks, 12 source-GDB checks, 1 unavailable eligible
profile-isolated pair and 1 explicit source-QA check. Source QA remains a separate
source-etl gate; local source verification is recorded above. That full run predates
the subsequent mount-only repair and its four new configuration regressions.

Execution policy: all project code, scripts, tests, builds, data processing, and
evidence or hash generation run inside Docker for every agent tier. The host is
limited to repository inspection/editing, Git and Docker CLI operations, and thin
Docker launcher glue. Host test runners, direct data parsers, and host evidence or
hash processing are prohibited; the former direct-file PowerShell parser exception is
removed. If Docker or the required image is unavailable, stop execution rather than
falling back to a host runtime.

Docker-only correction verified: evidence hashing/JSON generation and the post-tool
diagnostic now execute in the artifact container. Legacy direct FileGDB PowerShell
parsers refuse host execution. The evidence launcher passed end to end with
`-LocalImage`; the expanded offline fast gate passed **94 tests, 2 skipped**, with
lint/types/launcher checks clean. Actual Copilot hook-runner integration and the
published image remain unverified; the post-tool diagnostic cannot prevent writes.

- Shared instructions now live in root `AGENTS.md`; Copilot retains a thin adapter.
  Active spatial instructions now follow ADR-0005/0008/0009 instead of requiring
  global connectivity or invented zero-cost room connectors.
- The published image digest is recorded in Compose from successful GitHub Actions
  run `34501691967` (commit `7b92a8c7e17dc95da2d798b8abd5c94aec8c689a`).
  This machine's registry inspection returned HTTP 403. Published-image execution
  remains unverified here; local checks use existing `wayfinding-build:local`.
- HTTP fixes reject malformed profiles, bound admission before thread creation,
  and set a five-second idle socket timeout. Client fixes recompute profile changes,
  reject stale route responses and cancel routing after clear during room inspection.
- Current model routing preference: use large models for planning, orchestration,
  architecture and final judging; use smaller models for bounded mechanical edits,
  routine documentation and gate execution. Escalate ambiguous, security-sensitive
  or GIS-logic work to a large model.
- Coordination preference: the accountable lead should proactively delegate independent,
  bounded tasks to multiple concurrent agents, with clear file ownership; all agents
  follow the Docker-only project execution policy above.
- Obsolete DT-002 service tests now follow ADR-0006. Two DT-003 error-path tests use
  temporary source directories rather than requiring private GIS data.
- `make fast` and `make gates` are available. The new PR validation workflow runs
  source-independent fast checks with external networking disabled. It is not yet
  pushed/activated or configured as a required branch check.
- Earlier Docker-only checks: 94 passed, 2 skipped; Ruff, Pyright and launcher checks passed.
  Artifact QA: 23 passed, 1 skipped. Source layer-count QA: 1 passed in an offline
  source-ETL container. Both ETL and artifact Compose services disable external networking.
  New HTTP/client regressions were observed failing before implementation.
  Earlier full suite: 419 passed, 15 skipped; initial coverage gate failed at 82.77%.
  Supplemental synthetic extraction and evidence-regeneration tests raised combined
  coverage to 85.38% with no production changes and the 85% floor unchanged.
  This is full-plus-supplemental evidence, not a second clean full invocation.
  Details and limitations: `docs/reports/CODEX-TAKEOVER.md`.

DT-015 is **in progress**, not approved. A real second-device machine-name LAN check
remains unverified. No source/artifact promotion, data rebuild, existing-stack teardown,
push or publication was performed.

Next: restore published-image pull access and repeat gates with that exact image;
activate PR validation/required checks and complete physical LAN acceptance. Then
resume the revised-source comparison as a separate
planned ticket. `make etl` remains a legacy no-op; use explicit ETL stage targets
until an isolated rebuild/promotion workflow is implemented.

## Historical delivery record (superseded by current takeover status above)

**Phase 0 — complete.** Data profiled and documented
([docs/01-data-findings.md](01-data-findings.md)), system designed
([docs/02-system-design.md](02-system-design.md)), and the delivery harness scaffolded
([docs/03-harness-design.md](03-harness-design.md)): `.github/agents/`, `.github/prompts/`,
`.github/instructions/`, `.github/copilot-instructions.md`, `docs/DOD.md`, this file.

**Phase 1 ETL — in progress.**
- **DT-001 (harness bootstrap)**: Complete & approved. Skeleton `packages/wayfinding/`, `infra/docker-compose.yml` test service, `Makefile` gates (`test`/`lint`/`type`), ADR-0002.
- **DT-002 (ETL infrastructure & schema)**: Complete & approved. `etl` service in `infra/docker-compose.yml`, `make etl` target, `category_mapping.yaml` (all 62 `USE_TYPE` values), `schema.py` (7 Pydantic schemas with EPSG:26910 native CRS metadata), `run.py` (entry point). 19 passed, 2 skipped, 96.67% coverage.
- **DT-003 (extract layers to GeoPackage)**: Complete & approved. `extract.py::extract_to_gpkg()` function, `make etl-extract` target, `build/wayfinding.gpkg` with 14 layers (7 EPSG:26910 native 3D, 7 EPSG:4326 web 2D), 158,694 records (79,347 features × 2 CRS). 51 tests passed, 2 skipped, 95.52% coverage. Lint/type clean, data-QA PASS, judge APPROVE.
- **DT-004 (normalise tables)**: Complete & approved. `normalise.py` with 5 normalisation functions transforming raw layers into 6 tables (facility 3, level 11, unit 1017, landmark 40, detail 48728, door 6865; total 56,664 normalised records) stored as 12 dual-CRS layers in `build/wayfinding.gpkg` (26 total layers: 14 raw + 12 normalised). Includes category mapping, in-memory landmark dedupe (LMK_28 kept / LMK_41 removed), accessibility provenance (`verified_by`, `verified_date`), centroid fallback (1016 geometry_centroid + 1 envelope_center_fallback for SFU_BURNABY_QUAD_2000_2017), door separation. ADR-0003 documents dual-CRS storage & provenance model. 105 tests passed, 2 skipped, 92.74% coverage. Lint/type clean, data-QA PASS, judge APPROVE. Commits: adb9196, fbaf84b, 221373d.
- **DT-005 (graph node snapping and raw pathway graph)**: Complete & approved. `graph.py` with `load_level_lookup()`, `snap_nodes()`, `build_raw_graph()` functions. Outputs: `build/graph_raw.pkl` (NetworkX MultiDiGraph, 15,582 nodes, 44,826 directed pathway arcs, 12.4 MB), `build/node_map.pkl` (44,978 entries: 44,852 pathway + 126 transition endpoints, 1.5 MB), `build/graph_raw_stats.json` (metadata). Node identity per ADR-0004 uses coordinate tuples `(x, y, vertical_order)` with 1 cm EPSG:26910 grid snapping and vertical_order from `level_26910` table (never Z). All 11 levels represented. 13 self-loops removed. Pathway edges only (mode='pathway'); transition edges deferred to DT-006. Bidirectional arcs with forward key `PW_{fid}` and reverse key `PW_{fid}_R`. Edge attributes: `{length_3d, mode, level_id, feature_id, geometry}` with reverse-arc geometries coordinate-reversed. Within-level connectivity: largest component 2,957 nodes (AQ 3000), highest fragmentation 253 components (AQ 6000, pre-contraction). ADR-0004 documents MultiDiGraph rationale, node-identity semantics, node-map vs graph-membership distinction, round-half-up quantization, parallel-edge keys, and pickle serialization. 155 tests passed, 2 skipped, 90.29% coverage. Lint/type clean, data-QA PASS (17 checks), judge APPROVE. Commit: 14652a9.
- **DT-006 (add transition edges to graph)**: Complete & approved. `graph.py` updated with `add_transitions()` function adding 63 transition features (42 stairs, 21 elevators) as 126 bidirectional directed edges (84 stairs arcs + 42 elevator arcs) to pathway graph from DT-005, producing `build/graph_with_transitions.pkl` (15,587 nodes, 44,952 directed arcs, 12.6 MB) and `build/graph_with_transitions_stats.json` (cross-level connectivity metadata). 85 transition endpoints protected from contraction via `is_transition_endpoint=True` node attribute. 5 transition-only nodes (endpoints not referenced by pathways) added with complete node-attribute contract derived from transition source rows. 2 express elevators (vertical_order 0→2) handled as single edges. Cross-level connectivity validated per ADR-0005 measured baseline: default routing profile (pathways + stairs + elevators) yields 816 connected components (down from 855 pathway-only baseline, largest component 7,436 nodes, 39 components bridged by transitions with 24 stairs-only contributions); the elevator-only, stairs-excluded profile yields 840 components (largest component 7,060 nodes, 15 components bridged by elevators). Severe pathway-network fragmentation is documented in ADR-0005; routing is limited to within-component origin/destination pairs. This is not wheelchair certification; unverified: door_width, path_width, slope, powered_doors, surface. 212 tests passed, 2 pre-existing skips, 88.19% coverage. Lint/type clean, data-QA PASS (30 checks), judge APPROVE. Commits: 2233feb, 0c89ce4, 031fc5c.
- **DT-012 (Phase 1 developer standup and teardown)**: Complete & approved. `tools/launch-stack.ps1` and `tools/launch-stack.sh` build and start persistent, healthy `artifact` and `source-etl` capability containers. `-Test` / `--test` optionally runs `test`, `lint`, `type`, and `dataqa` inside the running artifact container. Matched `tools/teardown-stack.ps1` and `tools/teardown-stack.sh` wrappers require the exact Compose project name printed at startup, destroy only that selected project, preserve volumes by default, and remove them only with explicit `-Volumes` / `--volumes`. The README documents paired PowerShell and POSIX start/destroy commands. Launcher-focused gates, teardown contract/dry-run checks, and Compose configuration pass; an actual PowerShell standup built the local image and both services reached `healthy`, but no real teardown was executed. Full-suite verification remains blocked by the pre-existing ADR-0006 `sha256:PUBLISHED_DIGEST_REQUIRED` placeholder, not by DT-012 behavior.
- **DT-013 (artifact-backed demo explorer)**: Complete and approved. The loopback-only `demo` service serves a visual SVG floor explorer directly from `build/wayfinding.gpkg`, with real facility/level controls grouped by global `vertical_order`, pointer/keyboard room and landmark selection, exact artifact identity/provenance, and a disclosed deterministic assistant. DT-014 extends this boundary with bounded routing; nearest-place, travel-time, live-status, LLM, and path-accessibility certification remain unavailable.
- **DT-014 (bounded indoor X-to-Y PoC)**: Implemented; routing/GIS integrity passed independent data-QA and judge review, but repository-wide DOD remains blocked by ADR-0006's unpublished `PUBLISHED_DIGEST_REQUIRED` image reference. The demo hash-verifies `build/wayfinding.gpkg`, `build/graph_contracted.pkl`, and `build/graph_contracted_stats.json`, builds immutable same-level approximate room anchors within 10 m, prechecks stable default/elevator-only reachability, and returns deterministic graph-only routes or explicit failures. ADR-0009 preserves the measured edge-induced 816/840 component baseline while assigning deterministic RFC 8785/SHA-256 query-time identities to profile-isolated nodes. Canonical evidence self-hash: `a37b834aa754acaeeee4611b1a65b2fc8b72cfe875c899c452e40e182d9cd360`. The elevator-only profile excludes stairs; room-to-anchor traversal and door width, path width, slope, powered doors, surface, closures, opening hours, door access, and elevator status remain unverified. Revised-source profiling and promotion are deferred and no revised GDB claim is made.

## What changed most recently

- **DT-014 bounded routing integrity passed:** The local demo now routes exact unit pairs over the accepted legacy contracted graph, renders returned per-level graph geometry and geometry-derived steps, and exposes attachment distances, canonical reachability identities, artifact hashes, and limitations. Disconnected, profile-isolated, invalid-edge, and unavailable cases fail closed; elevator-only routes exclude stairs without claiming verified step-free access. Focused DT-014 validation passed 80 tests with one factual skip; GIS data-QA passed. Historical gate statement; see current takeover status for fresh evidence.

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Historical next steps (superseded)

1. Complete ADR-0006's image publication workflow and replace the `sha256:PUBLISHED_DIGEST_REQUIRED` placeholder with the published digest.
2. Publish the hermetic build image, replace `PUBLISHED_DIGEST_REQUIRED` with its immutable 64-character digest, and rerun the full DOD gates so `judge` can issue repository-wide `APPROVE`.
3. Plan the independent revised-source evidence ticket: profile and rebuild in isolation, compare unit-pair reachability, and require a new ADR before any source promotion.
