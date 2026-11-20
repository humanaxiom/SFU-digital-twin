# Burnaby expansion — Applied Sciences Building

This screen started at merged pilot revision `fa7b24f`. Applied Sciences
Building was selected as the first expansion sample because the SFU directory
and Room Finder can be compared using a building number and acronym.

## Building identity

Facilities lists **Applied Sciences Building**, acronym **ASB**, building
number **038** and three floor levels. The SFU Room Finder polygon row records
campus `Burnaby`, acronym `ASB`, building code `038` and the display name
`Applied Science Building` (singular). The number is a string with a leading
zero. The agreement on number, campus and acronym supports a building-level
match despite the spelling difference. The exact indoor facility and floor
identifiers remain outstanding. [Facilities directory entry](https://www.sfu.ca/fs/campus-maps/directory-of-buildings/applied-sciences-building.html)

An HTTPS query from Docker for `Abbr='ASB'` on each named Room Finder layer
returned the same identity and native polygon geometry in EPSG:3857. The
SHA-256 of the geometry object serialized as sorted compact JSON was
`48efc9e080a7f6ad33e42f2eaf810355f271165ef62c53e5ec50fbec35249bfd`.
The service names identify the layers used for comparison. The retrieval
establishes their contents at review time. [2023 Building Basemap](https://viewsfu-prd.its.sfu.ca/fsgis/rest/services/RoomFinder/RoomFinder2023_CampusMap/MapServer/0) · [2024 Building Basemap](https://viewsfu-prd.its.sfu.ca/fsgis/rest/services/RoomFinder/RoomFinder2024_CampusMapB/MapServer/0)

## Local indoor coverage

The checked-in source review ran with the three immutable geodatabases
mounted read-only and `/workspace/data` masked. The legacy and revised
snapshots both contain the following inventory. All 1,210 raw unit IDs are
distinct and join to a level. Every level joins to a facility.

| Building | Recorded levels | Raw units |
| --- | ---: | ---: |
| Academic Quadrangle | 6 | 828 |
| East Concourse Cafeteria (ECC) | 1 | 33 |
| Strand Hall | 4 | 349 |

The revised snapshot adds 141 pathways with unassigned building and level.
The supplemental dataset includes 82 entrances, 82 main doors and 34 ramps,
with no facility/pathway join. The two delivery ZIPs match each other and the
81 extracted legacy files. The separate Mini-SFU sample identifies its
two buildings as fictional. None supplies an ASB indoor catalog.

`./tools/rebuild.ps1 -Action Review -RunId dt023-intake-20261120-fourth-a -LocalImage`
exited 0 in container `e061629726bc`, local image `d7b70c51d54d`. The report
under `build/experiments/reviews/dt023-intake-20261120-fourth-a.json` has SHA-256
`61fd2a0ff2ea690f1749a4fcd217bb03e8091c80a567ed7f499b9aedc04eae1b`.
Additional archive and join checks ran in Docker containers `e9c34eba248b`,
`756e30c7c62a` and `6950e300dad2`.

## Next data delivery

For ASB room search and routing, request the indoor facility key, exact
levels, keyed room geometry and the mapped path and transition records. A
cross-building journey further requires verified entrances and exterior network
joins. The counted floors in the directory supply context only. The
[Facilities request](../requests/GIS-DATA-NEEDED.md) lists the specific fields.

## Reproduce the footprint screen

From the repository root in PowerShell, provide an unused run ID. The intake
container contacts the official Room Finder service. The demo and the subsequent
map review use the resulting local file.

```powershell
docker run --rm --read-only --cap-drop ALL -e PYTHONPATH=/src --mount "type=bind,source=${PWD}/packages/wayfinding/src,target=/src,readonly" --mount "type=bind,source=${PWD}/tools,target=/tools,readonly" --mount "type=bind,source=${PWD}/build/experiments,target=/evidence" wayfinding-build:local python /tools/burnaby_footprint.py asb-review-01
```

Container `d487a8eb29f7` produced
`build/experiments/dt023-asb-footprint-final-20261120.json`. Two live runs
produced identical bytes. The source ring has 126 coordinates including its
closing position. Its projected area is 5,840.96 m² in EPSG:26910.

| Evidence | SHA-256 |
| --- | --- |
| Native response, canonical JSON | `de95eab4bbbd981e9e8a210a26ef526022590b22323bb37d33866b487dfb6161` |
| Screen contents, canonical JSON | `c5b23e2f23f7e910b504303096b690bee33499a94c3b57e2d55ee61f49f8d214` |
| Final output file | `8482ecd441fb9f9201af46a1528dc189b7cf80f4812858ab166f8dfa4b281494` |

## Open the local preview

Use the existing pilot GeoPackage, contracted graph and stats files under
`build/`. After running the footprint screen above, start the separate local
Compose project. The demo binds to loopback on port 18183 by default.

```powershell
$env:WAYFINDING_BROWSER_BUILD_IMAGE = 'wayfinding-build:local'
$env:WAYFINDING_OVERVIEW_FOOTPRINT = (Resolve-Path build/experiments/asb-review-01.json).Path
$stack = @('-p','sfudt-burnaby-asb','-f','infra/docker-compose.browser.yml','-f','infra/docker-compose.overview-preview.yml')
docker compose @stack up -d --wait demo
```

Open [the local overview](http://127.0.0.1:18183/), select **ASB**, then use
**Campus overview** to see the four buildings again. To replay the real browser
checks, set an unused `WAYFINDING_BROWSER_RUN_LABEL` and run
`docker compose @stack run --rm --no-deps browser`. Use
`docker compose @stack down` to remove this preview. This launch uses the
read-only base artifacts and one read-only ASB file under
[ADR-0026](../adr/0026-burnaby-overview-footprint-preview.md).

## Delivery verification

The final live screen `asb-admission-delivery-20261120.json` reproduced the
recorded screen hash. The offline renderer consumed that screen and the accepted
GeoPackage (SHA-256 `f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65`).
It produced `build/experiments/dt023-overview-20261120/asb-delivery.svg`, SHA-256
`da42de0575f10e4344b58d55f0c4c79f52c9755cac752dddd8d4e1aa85a419e5`. The
standalone map preserves polygon holes and uses a common metric scale and
distinct coverage labels for all four buildings.

To render that SVG from the matching inputs, mount the GeoPackage read-only
at `/input/wayfinding.gpkg`, the intake JSON read-only at `/input/asb.json`,
and a dedicated experiment directory at `/evidence`. Use the same read-only
source and tools mounts as the intake command, add `--network none`, and run
the following inside the local build image with an unused output name:

```sh
python /tools/dt023_overview_preview.py asb-review-map \
  --canonical-sha256 f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65 \
  --screen-sha256 c5b23e2f23f7e910b504303096b690bee33499a94c3b57e2d55ee61f49f8d214
```

The optional API adds one Room Finder record. Both the campus and facilities
collections distinguish indoor artifact provenance from the ASB footprint
source. The deterministic assistant’s artifact-only building list still cites
the three buildings it can locate in the GeoPackage. An initial review found
that it cited ASB as a GeoPackage record. The regression reproduces the error
and verifies the corrected list against the running preview.

Chromium against the unmodified pilot exited 1 on the expected scope mismatch
(`dt023-asb-overview-red`, browser `c433b8a7a43b`). The final ASB browser
probe exited 0 in `deb1ca3f6e02` on demo `6c2f75233322`. At 1440, 390 and
320 px it verified exact footprint geometry, pointer and keyboard selection,
both recorded spellings of the building name, empty ASB floor and room
coverage, and route preservation during ASB inspection. SH1001C → SH1003
returned HTTP 200 with the recorded 12 edges and 21.83 m in each viewport.
A request using an unmapped ASB room returned HTTP 404. Screenshots and
`results.json` are under `build/navigation-review/dt023-asb-overview-search-delivery/`.
Result SHA-256: `92f21d7555c72db280078a417023f552b07573bc4c6dbbbe21c5b978363c9e31`.
The page returned HTTP 200 through the published loopback port.

Without the optional footprint, the canonical `tests/browser/demo.cjs` replay
exited 0 with four real fixtures on desktop and mobile, plus the narrow layout,
delayed-response and HTTP 409 checks (85 reads, 33 POSTs). Its demo was
`6b1c38b7b5e2` and Chromium was `8f81a3a53ce3`. Result SHA-256
`7d3fcdafc770e736cca655350d3c3158785cfd46a8bf830e2910d7a6fa479957` is
recorded under `build/takeover-browser/dt023-asb-default-regression/`.

The final Docker package run (`8bf91c52d5a9`) passed **673 tests with 16
documented skips and 87.24% coverage** in 467.82 seconds. Full skip reasons
are in `build/dt023-asb-package.log`. The local Compose artifact service ran
Ruff, Pyright, launcher checks and artifact QA (23 passed, one skipped, 665
deselected). All commands exited 0. The 22 focused intake, rendering and
application checks also passed. Chromium opened the final standalone SVG
offline and rendered `asb-delivery.png`. Visual inspection confirmed the four
labels, scale, AQ courtyard and ASB coverage distinction.

Independent review approved the opt-in local overview, including a live check
of the assistant attribution fix, read-only mounts and both mobile and desktop
screenshots. ASB indoor routing and wider campus admission remain open.
