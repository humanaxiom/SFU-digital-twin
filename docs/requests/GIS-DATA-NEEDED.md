# Data needed from GIS — ECC, AQ and Strand Hall

We have the three local geodatabases. Please provide the following corrections or
reference tables, using stable feature IDs so we can join them to those snapshots.

| Priority | Need | Why |
| --- | --- | --- |
| 1 | Building and level assignments for revised Pathways FIDs **22427–22567** (141 records). Confirm whether each is indoor, outdoor or a building connection; provide its intended connection points. | These records have no facility/level IDs, so we cannot safely integrate them. |
| 1 | Verified room-door-to-path connections, with room ID, door ID/location, floor ID and connected pathway ID. Identify non-public or restricted doors. | Current routes start/end near rooms; the connection to a real doorway has not been verified. |
| 1 | Stair/elevator reference: stable connector ID, actual served floors, entry/exit locations on each floor, public label and access restrictions. Confirm express elevators and any disconnected landings. | We need unambiguous floor-change instructions and cannot infer intermediate stops. |
| 2 | A check of apparent gaps in the indoor network: intended junctions, missing connecting paths and intentional separations. | Many room pairs currently have no connected mapped route. We must not bridge gaps by guesswork. |
| 2 | Authoritative building/floor display names and, where available, signed corridor/landmark names linked to route locations. | Directions should match signs people see, rather than internal GIS identifiers. |
| 2 | For any accessibility claim: verified widths, slopes, surfaces, powered doors, access restrictions and elevator availability, with survey date and verifier. | “Elevator only” currently means stairs excluded, not verified accessible. |

Please also confirm the intended connected chains for AQ3000 Pathways **9321,
9328, 9332, 9333, 9346, 9347, 9348, 9352, 9353, 9354, 9356**. Their parts connect when
reordered; our importer currently assembles them incorrectly. We will fix the importer
and do not need the original files edited in place.

Preferred delivery: a versioned FileGDB/GeoPackage update or keyed correction table,
with source snapshot, field definitions, CRS/vertical datum, revision date and verifier.
Keep unknowns explicit. UI improvements can proceed while these items are resolved.

## Campus overview and interbuilding routing extension — DT-023

For the planned Burnaby campus overview and routes between buildings, please also
provide:

| Priority | Need | Why |
| --- | --- | --- |
| 1 | Complete Burnaby facility inventory with stable IDs, official names/acronyms/aliases, footprints, operational status, and a crosswalk to Room Finder and existing indoor `FACILITY_ID` values. Confirm whether residences, leased, service and restricted buildings are in scope. | The supplied indoor sources contain only AQ, ECC and Strand Hall. We cannot define or display “all buildings” authoritatively from them. |
| 1 | Classification table for revised Pathways FIDs **22427–22567**, identifying indoor hallway, outdoor sidewalk, covered walkway, bridge, tunnel, stairs, ramp, plaza or non-routing linework; include grade/level, direction, public access, intended junctions and verification source. | These 141 unassigned features total 12,800.80 m and may include the missing AQ–Strand/campus network, but their current attributes cannot establish safe topology. |
| 1 | Connected, noded campus pedestrian centerlines with explicit same-grade junctions and grade-separated crossings for walkways, plazas, crossings, stairs, ramps, bridges and tunnels. | Intersecting or coincident geometry does not prove that two paths connect. Google Maps or visible proximity cannot replace an authored network. |
| 1 | Stable portal relationship for every routable public entrance: entrance ID → facility/local level → door ID → indoor path/node → outdoor path/node, with surveyed position, label, direction, hours/restrictions and verification date. | Entrance and door points in `AdditionalData_Testing.gdb` have no authoritative facility/path relationship and therefore cannot join the two graphs. |
| 1 | Horizontal CRS and vertical datum/reference, including the meaning of zero or missing Z and the relationship between local floor names and campus elevations. | Most revised additions and all supplemental points contain Z=0; overlapping paths and entrances cannot safely be assigned a grade by inference. |
| 2 | Current restriction and maintenance fields: one-way/public/staff/service access, opening hours, construction closures, seasonal treatment and accountable data owner. | Campus routes can change with time and operating policy. Unknown values must remain explicit. |
| 2 | For a later accessibility claim: current slope/cross-slope, clear width, surface, curb ramps, powered-door operation, step-free continuity and elevator access/status. | Ramps or an elevator-only graph do not independently prove an accessible journey. |

Please prioritize the apparent exact-endpoint review candidates: SH features **22429**
and **22452**, and AQ features **22471, 22473, 22497, 22498, 22534, 22540,
22562**. Features **22496** and **22561** also intersect both AQ and ECC footprints.
These are investigation leads only; please state explicitly whether each contact is an
intended, public, same-grade route connection.

The fresh DT-023 audit found that **22562** contacts AQ3000 feature **5150** and
AQ2000 feature **11921** at identical XYZ. Please resolve its actual grade and
intended attachment explicitly; coordinate equality cannot select between these levels.
See `docs/reports/DT-023-GIS.md` for the read-only source audit. This request is
prepared locally and has not been sent.

For acceptance, every routable building must have a verified public entrance; every
published portal must have authored indoor and outdoor attachments; every path crossing
must state its grade/connectivity; and stable feature IDs must survive future exports.
