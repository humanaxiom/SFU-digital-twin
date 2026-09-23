# 18. Exact source-vertex topology is the rebuild default

Status: accepted, 2026-09-23.

## Context

The accepted `endpoint-v1` graph preserves Strand Hall's six recorded stair
transitions but omits pathway junctions where one source feature ends at an exact
interior vertex of another feature. The reported `SH1036` to `SH3050.1` route is
therefore disconnected even though the immutable source contains an exact,
same-level chain to recorded stairs.

The isolated `exact-shared-vertices-v1` implementation and source-to-candidate
evidence from DT-022 already established that these are authored XYZ vertices. It
splits native single-part pathway lines at those vertices, preserves their source
spans and authoritative length, and rejects ambiguous snap-cell collisions. It does
not use proximity, interpolate intersections, bridge gaps or infer a level.

Fresh 2026-09-23 reconstruction confirms the user-reported route changes from HTTP
409 to a 90.70 m route using recorded stairs `TR_62` and `TR_61`. Exact topology
makes 310 of 313 Strand rooms reachable to at least one other Strand floor. Strand
level 100 remains limited because its recorded stair endpoint has no authored
pathway attachment. Strand has no recorded elevator transition.

## Decision

Use `exact-shared-vertices-v1` as the default for every new graph extraction and
launcher-driven rebuild. Keep `endpoint-v1` available as an explicit comparison
mode. Manifests created before topology configuration existed continue to resolve
to `endpoint-v1`; changing the new-build default must not reinterpret old lineage.

Promotion remains an explicit deployment action after a sealed source-to-candidate
build, full Docker gates, data QA and browser/API end-to-end checks against the
candidate. Generated artifacts stay outside Git and retain their manifest hashes.

Add `SH1036` to `SH3050.1` as a browser/API regression fixture. The fixture must
exercise clickable floors and rooms, the destination selector, route submission,
journey-floor selection and Previous/Next across a floor transition.

## Consequences

New rebuilds gain the source-authored connectivity previously hidden by endpoint
only import. Component and reachability hashes change with the rebuilt graph.
Historical accepted-artifact counts remain historical and must be labeled as such.

This does not authorize inferred room-door connectors, near-coordinate joins,
outdoor links, cross-building links or accessibility claims. Room anchors remain
approximate and their path to a doorway remains unverified.
