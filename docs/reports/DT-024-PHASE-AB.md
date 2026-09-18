# DT-024 Stage A/B — navigation foundation

Date: 2026-09-17. Branch: `feat/dt-024-navigation-foundation`, based on
`787462a388a47a720811c23ed3e8dabc25988777` (documentation PR #3).
Status: Stage A/B navigation foundation implemented and locally verified. Remote
integration is pending explicit approval after automatic review rejected the
combined commit/push command. The user subsequently authorized a local commit;
push and merge remain pending approval.

## Delivered boundary

The first increment implements the floor/navigation subset of
[DT-024](../plans/DT-024.md) under [ADR-0017](../adr/0017-navigation-state-and-journey.md).
Buildings remain discoverable, floor options contain only exact levels belonging
to the selected building, and Open floor works for an already-selected level.
Selection remembers a valid level per building with order-0/first-level fallback.

Client state owns requested/displayed floor identity and request revisions. Scene,
room and assistant responses cannot overwrite newer intent. A route accepted
after independent browsing is retained without moving the map; Return to route
restores its selected step. Clear cancels route-owned loading while preserving an
independent floor request and camera. Replacement also cancels old route-owned
scenes. Loading and failure distinguish the requested floor from the retained
map; room inspection and route cleanup cannot erase those messages. Retry is
explicit. A step commits after its scene loads; a first route instruction is
labeled loading or unmapped preview until its floor is available.

No HTTP/schema, graph, artifact, ETL or deployment configuration changed. The
existing client file retains presentation and route state until later phases;
this is not a claim that all DOM-derived endpoint state has been removed.

## Test-first and review evidence

All execution took place in Docker. Large-model agents (`gpt-6-astra`) owned
architecture/regression review and the lead integrated production changes. A
smaller worker (`gpt-5.6-luna`) owned the bounded Chromium harness. Independent
review identified additional route-scene and status-ownership races, each
captured RED before its fix.

Final independent judgment: `/root/phase_ab_tests` (`gpt-6-astra`) **approved the
bounded local Stage A/B implementation** after reviewing the final combined diff,
full-suite/focused-delta evidence and both final browser result files. No material
remaining Stage B blocker was found. The lead inspected desktop/mobile screenshots;
the new Open floor control is at least 44px tall. `git diff --check` passed.
This judgment does not authorize remote publication or close the later phases.

- Initial RED covered building/floor identity, explicit floor entry, failure/Retry,
  stale room details and late route versus newer floor selection. Scene ordering,
  Clear and assistant ownership cases extend this foundation.
- Concurrent assistant lookup RED failed before assistant revision ownership.
- `replacement_pending_step`: RED 1 failed/9 deselected; obsolete route scene
  painted AQ2 after replacement failed, rather than retaining AQ0.
- `retained_room_loading`, `retained_landmark_loading`, `clear_scene_error`:
  RED 3 failed/10 deselected; inspection/Clear erased loading/failure text.
- `initial_route_pending`: RED 1 failed/13 deselected; the new instruction appeared
  before its floor and remained unqualified after failure.
- Final focused command: `docker exec sfudt-wayfinding-18000-artifact-1 env
  PYTHONPATH=/workspace/packages/wayfinding/src pytest
  packages/wayfinding/tests/test_dt024_navigation.py --no-cov -q`:
  exit 0, **14 passed** in 0.80 seconds.
- Earlier integrated client/static checks: **37 passed**, 605 deselected. Existing
  global-order picker assertions were migrated to the accepted exact-ID contract;
  route geometry and safety assertions remain.
- Final integrated client command covered `test_dt024_navigation.py`,
  `test_dt023_client.py`, `test_dt013_static_client.py`, `test_takeover_client.py`
  and `test_dt018_client.py` with `--no-cov -q` in the artifact container:
  **22 passed** in 1.38 seconds, exit 0.

## Final gates and end-to-end evidence

The full Docker gate passed: **630 passed, 16 skipped, 86.25% coverage** in
261.69 seconds, exit 0. Its collection preceded the final first-instruction
regression; the final focused rerun separately covers all 14 DT-024 cases.
This is full-suite plus focused-delta evidence, not a second full-suite claim.
Durable full log: `build/navigation-review/dt024-stageb-full-test.log`.

The Makefile gate commands were executed directly in the existing artifact
container, avoiding nested Docker and PowerShell exit-status translation:

```text
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 sh -lc 'exec env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests > build/navigation-review/dt024-stageb-full-test.log 2>&1'
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src ruff check packages/wayfinding
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src pyright packages/wayfinding/src
docker exec -w /workspace sfudt-wayfinding-18000-artifact-1 env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov -o cache_dir=/tmp/dt024-stageb-dataqa-cache
```

Ruff passed; Pyright reported zero errors/warnings/information. Artifact data-QA
passed **23 tests, 1 skipped, 622 deselected** in 10.32 seconds. All exit codes
were 0. Its separate cache avoided collisions with the concurrent full suite.
The full suite's skips are 2 checks requiring Docker CLI inside the artifact
container, 12 extraction checks requiring the deliberately unavailable source
GDB, 1 source-QA check requiring the source-etl mount, and 1 check with no eligible
profile-isolated same-anchor pair in the accepted artifact. The last is also
the data-QA skip. No source/build change required source-to-candidate execution.

Launcher and boundary commands `sh tests/gate/test_launch_stack.sh`,
`sh tests/gate/test_no_host_python.sh`, and `sh tests/gate/test_rebuild_launcher.sh`
all exited 0. They ran inside the artifact container against temporary
LF-normalized copies of `tools/`, `infra/`, `tests/gate/` and `Makefile`, using
Docker Python `TemporaryDirectory` and `subprocess.run`; repository scripts were
not changed. Log: `build/navigation-review/dt024-stageb-launchers.log`.

The final Stage B browser harness passed at **2026-09-17T22:55:31.930Z**:
five checks cover all 11 exact floors, a nonvacuous native ArrowDown floor change,
44px Open floor, delayed route/Return, and retained-scene HTTP 503/Retry. There
were no uncaught errors. Evidence and inspected screenshots:
`build/navigation-review/phase-b-final4/navigation-results.json`.

The first canonical browser run, `dt024-stageb-final`, exited 1 because its helper
tried to focus Next immediately after starting a cross-floor load. Next is now
correctly disabled until that scene settles. The helper now calls the existing
`assertSelected` after choosing the middle step, preserving geometry assertions
before testing keyboard Next. That failure evidence is retained at
`build/takeover-browser/dt024-stageb-final/results.json`; the corrected final run
uses label `dt024-stageb-final2`.

The corrected canonical run **passed, exit 0**, from
2026-09-17T22:57:08.782Z to **2026-09-17T22:59:40.475Z**. Both desktop 1440x1000
and mobile 390x844 exercised `aq_elevator`, `aq_long_corridor`, `aq_stairs`, and
`strand_corridor`, with API/geometry parity, camera, campus, floor instructions,
pointer/keyboard and layout checks. Additional checks covered disconnected
elevator-only routing, incomplete endpoints, out-of-order scene/step/availability,
Clear during step loading, and 320px/reduced-motion navigation. It recorded
**242 reads and 39 POST requests**. Final results and screenshots:
`build/takeover-browser/dt024-stageb-final2/results.json`.

The canonical browser/API runner uses the deployed demo's network namespace,
read-only code/fixture/artifact mounts, and a writable evidence mount. Exact
corrected command (run after the final production/CSS changes):

```text
docker run --rm --init --shm-size=1gb --network container:sfudt-wayfinding-18000-demo-1 --workdir /workspace --mount type=bind,source=C:/repos/sfudt/ghcp/packages/wayfinding,target=/workspace/packages/wayfinding,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/tests/browser,target=/workspace/tests/browser,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/docs/reports/DT-015-demo-routes.json,target=/workspace/docs/reports/DT-015-demo-routes.json,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/wayfinding.gpkg,target=/workspace/build/wayfinding.gpkg,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/graph_contracted.pkl,target=/workspace/build/graph_contracted.pkl,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/graph_contracted_stats.json,target=/workspace/build/graph_contracted_stats.json,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/takeover-browser,target=/workspace/build/takeover-browser --env WAYFINDING_BROWSER_BASE_URL=http://127.0.0.1:8080 --env WAYFINDING_BROWSER_RUN_LABEL=dt024-stageb-final2 mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db node /workspace/tests/browser/demo.cjs
```

Local runtime: `sfudt-wayfinding-18000-demo-1`, with the repository client mounted,
http://127.0.0.1:18007/. This uses the supported local Docker image override, not
verification of published-image access. Artifact execution uses
`sfudt-wayfinding-18000-artifact-1`.

Artifact container ID:
`5f338a0781d62c22601fec45a29b65f827ea3b94a522b2658130b15126fe2612`.
Demo container ID:
`a75cd93b32a524b404a61eca7da99c46222c10ecc4185822eef964d0a35bc292`.
`docker inspect --format '{{.Name}} {{.Id}} {{.Image}}'` recorded both identities.

- Build image: `sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`.
- Chromium image: `mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`.
- GeoPackage: `f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65`.
- Graph: `ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d`.
- Stats: `2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1`.

Hashes were generated inside Docker with `docker exec -w /workspace
sfudt-wayfinding-18000-artifact-1 sha256sum build/wayfinding.gpkg
build/graph_contracted.pkl build/graph_contracted_stats.json` (exit 0).
The actual published host-port probe also exited 0, returning `status: ok`,
routing enabled, and all three matching hashes:

```text
docker run --rm mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db curl -fsS -H Host:localhost:18007 http://host.docker.internal:18007/demo/v1/health
```

## Remaining phases and limits

The full ticket remains open. Stage C adds searchable From/To, explicit endpoint
actions, draft/commit and honest retained-route profile labeling. Stage D fixes
journey visit → Next/Previous synchronization, replaces exploration stepping with
Return, and delivers mobile instruction placement and scene/cache integration.
The original journey-tab/Next mismatch is deliberately not claimed fixed here.
Stage A's journey-specific RED work accompanies D; A/B here names the navigation
foundation delivery, not completion of every row in the full acceptance matrix.

Native endpoint dropdowns and existing automatic endpoint/assistant route actions
remain until C. Current fixtures cannot certify physical navigation, verified
accessibility, outdoor connections or source correctness. No candidate artifacts
were promoted. Source-to-candidate verification is not applicable to this UI-only
increment. Existing DT-017 and DT-023 data gates remain open.
