# DT-024 — Scoped room search for directions

This delivery covers the N05 room-search interaction in the [Stage C plan](../plans/DT-024.md).
The app joins its existing searchable room catalog to exact level and facility
records. Building ID, building name, building acronym and room ID are the
Facilities-authoritative search fields. Route requests identify rooms by unit ID.
The existing endpoint submission rules apply. The separate draft and Preview
route workflow remains in the plan.

## Browser regression

Before implementation, the pinned Chromium container opened Directions in the
isolated `sfudt-dt024-search` demo and failed on the missing From search control
at `2026-11-20T01:49:54.078Z` (exit 1). RED output is in
`build/navigation-review/dt024-search-red/results.json`. This demo uses the
existing `sh-navigation-exact-20260923` artifacts read-only.

The native search field, building and floor filters, result list and explicit
selection button are the interim N05 controls. Their actions feed the same
endpoint workflow as the existing menus. Two Strand rooms have the recorded
ID SH110. Selecting the exact floor disambiguates them, and the Strand 100
room has no mapped connection from SH1036 under the default profile.

| Isolated search demo | Identity |
| --- | --- |
| Container | `c030ed51bcbf4c7b4a60e24bfc26e8aa322b8edf9a961018efa83f14ad6b217c` |
| GeoPackage SHA-256 | `da44fc5683169c53efcc0b2080cea4419ff40833dad8fb47c8b76051ec656eac` |
| Contracted graph SHA-256 | `93c2ff2994e6e564adecae3506175f2c0047948e1d84e44045d2c70267071d46` |
| Graph stats SHA-256 | `9a678cb044f6c76d3abf61bfa57a0e56fafb00efb0d181f5a7906492b23a6cfb` |

Git baseline was `5ca5186329e5dcf9df28a4f512280d7fc6c2d299` with inherited
local work. The package gates use the local Docker image
`sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`.
The pinned Playwright image is
`mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`.

## Package and state checks

Docker pytest passed 39 focused navigation and static client cases. All 22
Node route-options state tests passed. Artifact QA passed 23 cases with one
expected artifact-specific skip and 648 deselected. Ruff and Pyright passed.
All three launcher and host execution checks passed. Commands ran in the
`artifact` service with the local Compose override, or in the pinned browser
container for Node. Package checks used `PYTHONPATH=/workspace/packages/wayfinding/src`.

```sh
pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov
ruff check packages/wayfinding
pyright packages/wayfinding/src
sh tests/gate/test_launch_stack.sh
sh tests/gate/test_rebuild_launcher.sh
sh tests/gate/test_no_host_python.sh
node tests/gate/test_route_options_state.cjs
```

## Browser fixtures and verification setup

The search probe uses the real catalog of 1,017 rooms in 11 levels across three
facilities. It checks exact and partial room ID, each building field, duplicate
labels, and empty results. SH1036 → SH3050.1 uses Strand 1000, 2000 and 3000,
with 396 guidance coordinates. Direct API calls check connected and disconnected
destinations among 1,016 choices, including HTTP 409 for the floor-100 SH110.
Endpoint controls are exercised using native pointer and keyboard events.

An overlapping rerun shared one client IP between two browser containers and
hit the demo's read rate limit. `/app.js` and `/styles.css` returned HTTP 429.
The serial search replay on the isolated network uses a separate client address.

The frozen search replay passed all 15 checks. At 320 px it selected the
destination first, set the origin, and observed exactly one route request. It
then replaced the origin while delaying the real availability response. The
client cleared the incompatible destination and sent zero further route requests.
Results and screenshots are in `build/navigation-review/dt024-search-final-serial/`.

```powershell
docker run --rm --init --shm-size=1gb --network sfudt-dt024-search_candidate --workdir /workspace --mount type=bind,source=C:/repos/sfudt/ghcp/tests/browser,target=/workspace/tests/browser,readonly --mount type=bind,source=C:/repos/sfudt/ghcp/build/navigation-review,target=/workspace/build/navigation-review --env WAYFINDING_BROWSER_BASE_URL=http://demo:8080 --env WAYFINDING_BROWSER_RUN_LABEL=dt024-search-final-serial mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db node /workspace/tests/browser/room-search.cjs
```

For the canonical four-route regression, the local build image backs a separate
demo (`d7a559816459`), and the pinned browser container (`2ca5961e1e56`) runs
the existing desktop/mobile suite against the accepted artifacts.

```powershell
$env:WAYFINDING_BROWSER_BUILD_IMAGE='wayfinding-build:local'
$env:WAYFINDING_BROWSER_RUN_LABEL='dt024-room-search'
docker compose -p sfudt-room-search-canonical -f infra/docker-compose.browser.yml up --force-recreate --abort-on-container-exit --exit-code-from browser
```

The canonical browser exited 0 after 308 reads and 33 POSTs. The four fixtures
covered AQ2035.2 → AQ5046 (elevator only), AQ5029 → AQ5044, AQ1010 → AQ2103
and SH1001C → SH1003. Results are at `build/takeover-browser/dt024-room-search/results.json`.
The separate candidate cross-floor replay passed all 12 checks, including 14
route calls (two injected HTTP 409s) and delayed availability. The serial replay
used the same Docker command as the search probe with `crossfloor-room-picking.cjs`
and label `dt024-search-crossfloor-final-serial`. Both isolated Compose projects
were removed. All three candidate artifact hashes matched after verification.

The first full pytest run had 654 passes, 16 skips and two failures in
`test_dt015_static_client.py`. Both static assertions assumed the second map
click submitted a route inside `activateRouteEndpoint`. The assertions now
follow its shared destination handler, verifying one submission and the early
return for a duplicate endpoint. All 11 tests in that file then passed.
No runtime changes followed the browser checks. No source or build inputs
changed. Registry publication, physical LAN and external TLS were outside the
local application checks.

Final Docker `pytest packages/wayfinding/tests -o cache_dir=/tmp/room-search-final`
exited 0 with 656 passed, 16 expected skips and 86.96% coverage in 376.84 s.
The full log is `build/room-search/final.log`. The artifact-only gate skips
source-dependent, optional-tool and artifact-specific cases. Independent
`gpt-6-astra` review accepted N05 conditional on this full rerun passing. The
rerun satisfied that condition. The draft/Preview workflow remains open.

| Verified file | SHA-256 |
| --- | --- |
| Search browser result | `5c5b521622ae73aea28efe5732f990a230422bc7d4ff43ba6e183af4aba4b193` |
| Cross-floor browser result | `104c8b4da169d64b971e237436b377e974e36982747bd2167b5c0fd22a7daaee` |
| Canonical browser result | `aaf5338e830666a6856eb0ed3fd601244d49ce7355b3811361e3136703ed08a5` |
| app.js | `58925cdbf673f4c48fa62e0c0297084c3877426ce9bcb193d44ec59a680f6a00` |
| index.html | `75f4ddf37908dc4f23ed1b2f5224906a2a0da7249f3b87d08edb57c009863773` |
| styles.css | `207497981256d5690b5004baf731c9cba07898dd10d444eb94231fd301c36bb6` |
