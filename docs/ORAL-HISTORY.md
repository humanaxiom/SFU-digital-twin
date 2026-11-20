# SFU Indoor Wayfinding oral history

This history follows the repository from its August 2026 inception through the
November 20 Stage C delivery. The November review branch collects the client,
build and deployment increments developed on top of `5ca5186`. This history
reconstructs what happened from Git, plans,
accepted architecture decisions, delivery reports, and recorded feedback. The
[handoff](HANDOFF.md) is the place to resume work, and the [definition of
done](DOD.md) governs new acceptance.

## August 29–September 1 · An authored network set the direction

The initial question was how to add indoor directions to the room-finding
experience at SFU Burnaby. The Phase 0 profile found that the Esri ArcGIS Indoors
Information Model already supplied pathway and transition geometry for Academic
Quadrangle (AQ), East Concourse Cafeteria (ECC), and Strand Hall (SH). Its seven
indoor layers included 11 levels, 1,210 raw rooms, 22,426 pathways and 63
transitions. Routes could start from this authored network. The data also defined
the limits of the pilot. Floor numbers were local to buildings, and the separate
`vertical_order` field put AQ 3000, ECC 3000, and SH 1000 at the same campus order.
Door linework lacked clear widths and powered-operator evidence, and the source
included neither live outages nor access schedules. The original system design
described a broader product with FastAPI, MapLibre, a search index and an LLM
orchestrator. The subsequent demo delivered a smaller vertical slice.
[Data findings](01-data-findings.md) · [System design](02-system-design.md)

The repository started with a Phase 0 design and harness commit (`3d3f8dd`).
The original Copilot workflow borrowed test-first delivery and independent
review from two read-only reference repositories. It established a living
handoff, recorded architecture decisions, and set up containerized gates. DT-001
delivered the package and test/lint/type bootstrap. DT-002 established ETL schemas
and the category mapping. DT-003 extracted each raw spatial layer into native
EPSG:26910 and web EPSG:4326 versions. DT-004 added six normalized tables in both
CRSs, kept the 1,017 searchable rooms, deduplicated one landmark and separated
door linework. Geometry and routing calculations stayed in the native metric CRS.
[Harness design](03-harness-design.md) · [Package and container
conventions](adr/0002-package-layout-and-container-execution.md) · [Phase 1
plan](plans/PHASE-1-ETL.md) · [Dual-CRS schema](adr/0003-normalised-etl-schema-and-dual-crs-storage.md)

DT-005 used one-centimetre snapped XY and recorded vertical order for graph
nodes, keeping parallel arcs in a directed NetworkX MultiDiGraph. The pathway
graph had 855 components. DT-006 added 42 stair and 21 elevator transitions,
including two express elevator features, and measured 816 default and 840
elevator-only edge-induced components. Those counts became the baseline for
the original graph. A route could use its measured component and selected
profile. The elevator-only filter excluded stairs, and physical accessibility
remained unverified. DT-007 then disproved the estimate that the graph would
shrink to a few thousand arcs. Preserving junctions, transition endpoints and
nodes near rooms yielded 7,450 nodes and 19,884 directed arcs. The ticket
revised the compression expectations and kept the protection rules. Its 20
sampled shortest-path comparisons agreed.
[Graph identity](adr/0004-graph-construction-and-node-identity.md) · [Measured
connectivity](adr/0005-measured-connectivity-baseline-and-validation-gates.md) ·
[Contraction record](plans/DT-007.md)

## September 9–11 · A runnable demo exposed weaknesses in the delivery process

The developer launch and teardown scripts arrived with DT-012. DT-013 served a
loopback SVG explorer from trusted artifacts via a standard-library HTTP server.
DT-014 added deterministic exact-room routing and assistant directions over the
contracted graph. The initial room anchors selected a node on the exact same
level within 10 m and disclosed the offset. The route contains graph geometry and
graph distance, and the walk from a room to its anchor remains unverified. The
demo checks the GeoPackage and graph against recorded hashes before loading
trusted artifacts. ADR-0009 distinguished the historical component IDs from the
reachability IDs of isolated anchors. That distinction allowed truthful
disconnected and same-anchor results without changing the 816/840 historical
counts. An unpublished Compose image placeholder still blocked repository-wide
acceptance at the time.
[Developer lifecycle](plans/DT-012.md) · [Artifact-backed
explorer](adr/0007-dt-013-artifact-backed-demo-vertical-slice.md) · [Bounded
routing](adr/0008-bounded-indoor-routing-poc.md) · [Endpoint
reachability](adr/0009-edge-induced-profile-components-and-endpoint-reachability.md)

DT-015 introduced the click-to-route workflow and a bounded exception for an
attended, trusted private LAN demo. Manual endpoints, two room activations and
exact assistant directions shared one route request and renderer. The inherited
evidence omitted the planned Strand corridor example. The takeover restored it
with SH1001C → SH1003, a 21.8 m route on Strand 1000 over 12 pathway edges, along
with three AQ fixtures. Real Chromium exercised pointer and keyboard activation,
desktop and mobile layout, stale responses and assistant parity. A physical
second-device machine-name LAN check was still outstanding.
[Trusted-LAN decision](adr/0010-trusted-lan-demo-and-route-entry-parity.md) ·
[DT-015 plan](plans/DT-015.md) · [Replayable route fixtures](reports/DT-015-demo-routes.json)

Codex inherited the dirty DT-015 work from `998c477`. The initial full gate
showed eight failures and 82.01% coverage. Obsolete service assumptions and
source-dependent error tests contributed alongside the missing digest. The
takeover also reproduced a malformed-profile crash, weak admission controls and
stale client state, then fixed input validation, bounded connections before
thread creation, added a socket deadline and repaired request ownership. Shared
rules moved into `AGENTS.md`, and the Copilot files became adapters. The
Docker-only rule came to cover project execution, including diagnostics and
evidence generation. Publication run `34501691967` provided a real immutable
image digest. Local registry inspection returned HTTP 403, and later pulls
returned unauthorized. The documented local image kept Docker verification
possible on this machine. It supplied local execution evidence while access to
the published image remained unverified.
[Hermetic image and artifact lineage](adr/0006-hermetic-build-image-data-qa-and-artifact-lineage.md) ·
[Takeover plan](plans/CODEX-TAKEOVER.md) · [Takeover evidence](reports/CODEX-TAKEOVER.md)

The user clarified that all three geodatabases were already in repository-local
`data/`. A Docker read-only review confirmed that local legacy
`IndoorWayfinding.gdb` matched the
previous sibling copy byte-for-byte. It also found that the whole-repository
bind exposed the local raw inputs through `/workspace/data`. Fresh Compose
containers now mask that path, and only source-etl receives an explicit
read-only legacy mount. Earlier containers required recreation to acquire that
protection. The revised `IndoorWayfinding_AQ_SH_ECC_Revised.gdb` preserved the
legacy features and added 141 pathways
without facility or level IDs. The entrances, doors and ramps in
`AdditionalData_Testing.gdb` lacked
the authoritative joins needed for routing.
[Local source and mount review](reports/LOCAL-SOURCE-REVIEW.md)

DT-016 replaced the no-op build entry point with an isolated source-to-candidate
pipeline. Independent candidate runs agreed on graph, unit, anchor and reachability
semantics even though their output bytes differed. The legacy graph connected
33,361 of 516,636 eligible room pairs by default and 29,364 with stairs excluded.
Reconstruction also exposed eleven AQ3000 multipart features whose stored
sequence was noncontiguous. Four accepted contracted chains retained 41
non-source joins and distance/geometry disagreement. This gave DT-017 a specific
repair target. DT-016's fresh source-to-candidate rerun and its accepted-artifact
browser checks were separate runs against different artifacts. During this work,
the user made fresh Docker end-to-end verification a requirement for each new
delivery, including documentation-only changes. DT-019 later made
the rebuild launcher's missing-image diagnostics actionable and verified its
explicit `-LocalImage` path end to end.
[Isolated build decision](adr/0011-isolated-source-review-and-legacy-rebuild.md) ·
[DT-016 evidence](reports/DT-016.md) · [DT-019 launcher report](reports/DT-019.md)

## September 11–17 · Screenshots separated guidance, coverage and navigation

The user asked for clearer floor-by-floor guidance and authorized DT-018 after
the GIS request was written. The update added ordered floor visits, explicit
departure and arrival, and blue selected route spans. A shared local SVG
origin fixed broken strokes while retaining exact native coordinates. The
reported AQ1003 → AQ5053.2 route exposed a genuine cost/geometry disagreement,
so it received limited guidance with generic walking text and no walking
distance. DT-020 added profile-aware destination choices and visible failures.
DT-021 addressed a different screenshot, AQ303 → AQ3149. That route already
worked, but its camera framed a point-only start in a 16 m square. The map began
opening in useful current-floor context, with zoom and reset controls.
[GIS request](requests/GIS-DATA-NEEDED.md) · [DT-018 guidance](reports/DT-018.md) ·
[DT-020 availability](reports/DT-020.md) · [DT-021 camera](reports/DT-021.md)

AQ6071 revealed an actual importer defect. Its pathway endpoint coincided
exactly with a same-level interior vertex of another authored pathway, but the
endpoint-only graph skipped the junction. DT-022 built equivalent-source
endpoint and exact-vertex candidates. The exact mode split at supported
same-level XYZ vertices, conserved source lengths and skipped ambiguous snap
cells. It added 257,108 reachable room pairs in the default profile and 230,356
in elevator-only, with zero losses. AQ6071 went from one mapped destination to
696 in both profiles. This was an isolated experiment and the endpoint-only
default was still in place.
[Exact vertex decision](adr/0015-exact-source-vertex-junctions.md) ·
[DT-022 evidence](reports/DT-022.md)

DT-023 responded to the request to show Burnaby buildings and route between
them. The deliverable was a three-building campus overview with recorded
building selection and floor controls. The DT-022 candidate connected 8,220
room pairs in each direction between AQ and ECC for both profiles, and none
between Strand and either other building. An apparent revised pathway contact,
FID 22562, touched two AQ levels at identical XYZ. It could not pick an intended
grade. Campus expansion still needed a complete facility inventory, classified
pedestrian paths and verified doors linking authored indoor and outdoor nodes.
The dedicated Windows preview uncovered a deployment distinction when an
internal-only Docker network suppressed the published host port. Adding a bridge
restored the loopback binding, which was then exercised from Chromium through
the host port. PR #2 also synchronized building clicks with valid floor choices.
[Campus decision](adr/0016-campus-overview-and-coverage.md) · [DT-023 GIS
audit](reports/DT-023-GIS.md) · [DT-023 delivery](reports/DT-023.md)

A subsequent local refresh on September 16 used the local image and explicit
Compose path. It passed deployment smoke checks, then a task-based browser
review reproduced a late route taking back the map, a floor selection silently
changing the building and a journey tab causing Next to advance from the wrong
instruction. DT-024 split the overhaul into stages. September 17 Stage A/B
established stable buildings, exact building-scoped floor IDs, Open floor,
requested versus displayed scenes, Retry and Return to route. Request ownership
kept late completions from claiming newer map intent. The implementation reached
main after the user authorized integration (PR #4, implementation `111ecf1`).
[Navigation review](reports/NAVIGATION-REVIEW.md) · [State and journey
decision](adr/0017-navigation-state-and-journey.md) · [Stage A/B
report](reports/DT-024-PHASE-AB.md)

## September 23–October 8 · Clickable rooms and a public candidate

Feedback after PR #4 called for visible rooms, clickable buildings and floors,
and less scrolling. The next iteration put floor buttons above the map, offered
a visible room list with filtering, and moved secondary controls into expandable
panels. At that point, room clicks still set route endpoints automatically.
A cross-floor follow-up waited for availability, blocked known-disconnected
destinations without a route POST and kept origin A when replacing destination B.
The failure for SH1036 → SH3050.1 had a separate cause. All six recorded Strand
stair transitions existed, but the endpoint-only graph skipped pathway junctions
needed to reach them. DT-025 made the exact-vertex algorithm the default for
new builds and served the isolated candidate
`sh-navigation-exact-20260923`. It restored a 90.70 m route through SH1000,
SH2000 and SH3000 using recorded stairs. Strand level 100 remained disconnected
from its rooms, and no Strand elevator transition was recorded. The new
algorithm default and deployment did not promote the generated candidate into
the canonical accepted artifact set.
[Compact UI report](reports/DT-024-COMPACT.md) · [Cross-floor room picking](reports/DT-024-CROSSFLOOR-ROOM-PICKING.md) ·
[Exact topology default](adr/0018-exact-source-topology-default.md) · [DT-025
Strand verification](reports/DT-025.md)

September's DT-026 put a digest-pinned unprivileged nginx edge in front of
the candidate on public port 8007. It admitted only the expected hostname and
fixed the upstream Host. Chromium and outside HTTP probes exercised that
publication at the time. By October 8 the deployment was observed stopped;
DT-027 first repaired the PowerShell startup and teardown path, which failed
because the default Compose path was resolved during parameter binding.
DT-028 then used the router mapping the user confirmed. The documented
publication became public `sfuai.ca:8017` → local nginx 18087 → separate
candidate on loopback 18107. The developer stack remained on 18007. Outside
HTTP checks passed even though the local network timed out via the public
address, consistent with unavailable NAT loopback.
[DT-026 edge](reports/DT-026.md) · [DT-027 launchers](reports/DT-027.md) ·
[DT-028 router mapping](reports/DT-028.md)

DT-029 integrated both projects into normal repository-root startup and
added `unless-stopped` for the two public services. Isolated process-exit
tests confirmed automatic container restart. Recovery after a host reboot
would also require Docker Desktop startup, which the ticket did not exercise.
DT-030 served HTTPS on port 8017 using existing read-only certificate files,
redirected HTTP and kept certificate renewal with its existing owner.
PowerShell 7 and 5.1 startup, edge/back-end hash parity, real browser/API,
independent external HTTPS and isolated restart checks passed. That evidence
dates to October. The November client reports provide local browser/API evidence.
[DT-029 integrated startup](reports/DT-029.md) · [DT-030 TLS](reports/DT-030.md)

## November 19–20 · Facilities evidence, safer builds, and explicit Preview

The November repository review identified misleading accessibility labels,
legacy ETL commands that could overwrite accepted artifacts, a delayed
destination race and known multipart defects in the served graph. It also
recorded outstanding CI enforcement and publication concerns. DT-031 exercised
the sequence in which a destination click waits for availability and a newer
floor selection arrives. The older click can resolve its owned route without
moving the current scene or stealing room inspection. Independently versioned
destination choices also kept unsupported clicks from invalidating a valid route.
The verified repair covered pointer and keyboard interaction and narrow screens.
[November repository review](../REPOSITORY-REVIEW.md) · [DT-031 race repair](reports/DT-031.md)

Facilities supplied six answers. Building ID, Building Name, Building Acronym
and Room ID are the authoritative location fields, with department and common
names maintained manually. The current room/building schema is consistent, and
the export contract for additional buildings needs confirmation. The Facilities
app can mark restricted, closed and construction areas manually, but Facilities
has no automatic closures or after-hours feed. Campus Security may know locking
policy and schedules. Facilities has automatic-door locations, with detailed
width and elevator-dimension surveying still prospective. SNAP and physical
notices sometimes report elevator outages, and Facilities has no authoritative
automated feed. No walking-speed or elevator-wait standards were supplied.
DT-032 used this feedback to show recorded use and category with an explicit
physical-accessibility disclosure. The API retained its legacy tags for
compatibility. The next existing-data request asks for keyed snapshots of
manual restrictions and automatic doors, with survey coverage and live data
ownership still to be confirmed.
[Facilities answers](02-system-design.md#12-open-questions-for-stakeholders) ·
[Legacy tag decision](adr/0023-facilities-evidence-and-legacy-tags.md) ·
[DT-032 evidence](reports/DT-032.md)

DT-033 reproduced fixed-output deletion with disposable data, then retired the
five legacy stage targets. The supported launcher requires a new run ID.
Extraction stages output on the destination filesystem, replaces an existing
file atomically only when overwrite was authorized, and otherwise refuses to
clobber a competing output. Fresh source-to-candidate verification and a same-ID
refusal left the accepted files protected. With that protection in place,
DT-017 reconstructed all 11 affected legacy AQ pathways from unambiguous
exact native XYZ chains, carrying original part and vertex provenance. It also
preserved a contraction boundary between unequal native endpoints that shared
a snapped graph node. An exploratory run stopped on runtime drift. The completed
`dt017-legacy-20261119-b` run passed independent geometry, reachability and
candidate browser/API checks. It gained 697 reachable room pairs per profile
with zero losses. The running demo kept its existing artifacts. All 141
unassigned revised pathways remain in a fingerprinted exclusion ledger pending
reviewed facility/level assignments.
[DT-033 safeguards](reports/DT-033.md) · [Multipart
decision](adr/0025-exact-multipart-pathways.md) · [DT-017 candidate](reports/DT-017.md) ·
[Exclusion ledger](reports/DT-017-exclusions.csv)

On November 19 Stage C added scoped From and To room search, using the recorded
room ID and the three official building fields. The November 20 increment
finished the draft and explicit Preview workflow. Room activation now opens
inspection. Start here and Directions here, the selectors, Swap, the profile and
assistant directions edit the draft. Preview submits a snapshot of the draft.
The displayed route retains its own endpoints and profile until a successful
replacement, and Clear cancels pending work while preserving floor and room
inspection. Regressions caught early submission, stale availability, a
malformed success response, stale room details and a committed summary taking
on a replacement's pending/error styling. The final report records 662 Docker
tests passed, 16 expected skips, 86.96% coverage and independent scoped acceptance.
Fresh candidate and canonical browser/API checks covered the explicit workflow,
including SH1036 ↔ SH3050.1, a real elevator-only refusal, failed replacements,
pointer and keyboard use, and 320 px controls. The delivery report records this
as local verification on HEAD `5ca5186` with inherited working-tree changes.
[Stage C search](reports/DT-024-ROOM-SEARCH.md) · [Stage C
Preview](reports/DT-024-PREVIEW.md)

At the Stage C checkpoint, Stage D still owned the remaining synchronized journey, exploration/return,
persistent mobile instruction and scene-cache work. Stage E is integrated
acceptance for the full navigation ticket. Separately, the reconstructed
DT-017 legacy candidate awaits any promotion decision, and the revised and
campus inputs still need reviewed source evidence. The application remains the
bounded deterministic SVG demo. The [DT-024 plan](plans/DT-024.md), [handoff](HANDOFF.md)
and [GIS request](requests/GIS-DATA-NEEDED.md) record the work to resume.

The November 20 review branch brings the wayfinding implementation and its
earlier launcher, TLS and recovery work together. During the replay, the browser
test twice tried to preview a route before the destination selection had settled.
The test now waits for the selected room ID and checks that selection alone sends
no route request. With that change, the rebuilt candidate passed the same eight
route fixtures on desktop and mobile. The [handoff](HANDOFF.md) records the
container identities, result hashes and remaining deployment checks.

## From the three-building pilot to campus expansion

The next navigation pass used two real Academic Quadrangle elevator routes to
resolve different questions. One skipped a recorded floor. The other visited
the same floor twice, so selecting a floor by its label alone could put a user at
the wrong instruction. The client follows the chronological visit. Browsing a
room or the campus map preserves that instruction and offers Return to route.
On mobile, an early browser run put the transition and Next controls below the
viewport. The resulting change keeps them alongside the map.

The agreed geographic sequence starts with additional buildings across Burnaby
after pilot navigation acceptance. Other SFU campuses follow that expansion.
The next GIS request is a joinable building sample. Its verified footprint,
rooms, floors and pathways determine the coverage the demo can offer.
[Journey report](reports/DT-024-JOURNEY.md) · [Campus expansion plan](plans/DT-023.md)
