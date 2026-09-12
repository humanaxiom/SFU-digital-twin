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
