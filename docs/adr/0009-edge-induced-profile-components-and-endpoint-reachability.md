# 9. Edge-induced profile components and endpoint reachability

Status: Accepted
Date: 2026-09-10
Corrective refinement to: ADR-0008 §4

## Context

ADR-0005 establishes measured connectivity baselines of 816 default-profile components and 840
elevator-only, stairs-excluded components. Those values describe components induced by edges
permitted by each profile; they must remain unchanged by query-time endpoint handling.

ADR-0008 §4 requires every endpoint catalog record to carry a stable component ID for each profile.
That wording is incomplete for a contracted graph node that has no incident edge permitted by the
selected profile. Counting such retained nodes as components can inflate the ADR-0005 baseline.
Omitting them from endpoint reachability can instead cause null comparisons, accidental searches,
or rejection of a valid zero-edge request whose origin and destination resolve to the same anchor.

The distinction is especially relevant to `elevator_only`: a node incident only to stairs is not in
the edge-induced elevator-only graph, but it remains a deterministic endpoint anchor. This is a
reachability identity issue, not evidence of an elevator-only route. The profile continues to mean
pathways and elevators only, with stairs excluded; door width, path width, slope, powered doors,
surface, closures, elevator status, and room-to-anchor traversal remain unverified.

Inspection of the accepted DT-014 artifact set verifies three nodes isolated under the
`elevator_only` profile, but zero eligible searchable unit endpoints anchor to those nodes. An
accepted-artifact isolated same-anchor route fixture is therefore impossible without fabricating an
endpoint relationship. Synthetic graph/catalog tests can still prove the required zero-edge
semantics without misrepresenting the accepted artifacts.

## Decision

### 1. Preserve the measured counted-component baseline

For profile `p`, let `E_p` be the graph edges whose modes are allowed by that profile and let `V_p`
be only the nodes incident to at least one edge in `E_p`. Count weakly connected components in the
edge-induced graph `(V_p, E_p)`. Nodes retained in the artifact but absent from `V_p` are not counted
components.

This definition must reproduce ADR-0005 exactly: 816 counted components for `default` and 840 for
`elevator_only` on the accepted artifact set. ADR-0009 does not change, rebaseline, or relax those
values.

### 2. Give every endpoint a query-time reachability identity

For every eligible endpoint anchor and every profile, the endpoint catalog exposes:

- `component_id`: the counted component ID when the anchor is in `V_p`, otherwise `null`;
- `reachability_kind`: `counted_component` when `component_id` is present, otherwise
  `profile_isolated_singleton`; and
- `reachability_id`: the counted component ID for `counted_component`, or a deterministic
  profile-scoped singleton ID for `profile_isolated_singleton`.

The precheck compares `reachability_id`, never nullable `component_id`. Equal reachability IDs permit
routing evaluation. If both endpoints resolve to the same profile-isolated anchor, the service
returns a successful zero-edge, zero-distance same-anchor route without invoking shortest-path
search. Different reachability IDs return the profile-specific explicit `409` defined by ADR-0008
before any shortest-path search: `409 disconnected` for `default` and
`409 no_elevator_only_route` for `elevator_only`. This applies equally to two different isolated
anchors and to an isolated anchor paired with a counted-component anchor.

Same-anchor success proves only identity of the graph anchor. It does not prove a traversable
room-to-anchor segment, elevator availability, or any stronger accessibility property.

### 3. Canonicalize IDs and evidence deterministically

Canonical values use UTF-8 encoded RFC 8785 JSON with no trailing newline. A graph node is encoded
as the canonical JSON representation of its full ADR-0004 node-identity tuple; no display string,
Python `repr`, process hash, or NetworkX enumeration order participates.

- A counted `component_id` and its identical `reachability_id` are lowercase hexadecimal SHA-256
  of canonical JSON `{"kind":"counted_component","nodes":[...],"profile":<profile>}`, where
  `nodes` contains the component's canonical node values sorted by their canonical UTF-8 byte
  sequences.
- An isolated `reachability_id` is lowercase hexadecimal SHA-256 of canonical JSON
  `{"kind":"profile_isolated_singleton","node":<node>,"profile":<profile>}`.

The complete 64-character digest is authoritative. A UI may display a prefix, but persisted
catalogs, comparisons, responses, and evidence must use the complete digest. The algorithm label is
`profile-reachability-rfc8785-sha256-v1`.

### 4. Return auditable response and evidence fields

Every resolved endpoint in a success or route-related failure includes `unit_id`, `level_id`,
canonical `anchor_node`, `attachment_distance_m`, `component_id`, `reachability_id`, and
`reachability_kind`. The envelope also includes `profile`, `allowed_modes`,
`reachability_algorithm`, `component_semantics: "edge_induced"`, `component_count`, and the exact
`gpkg_sha256`, `graph_sha256`, and `graph_stats_sha256`. Existing ADR-0008 source status, route
algorithm version, warnings, and elevator-only disclosure remain required.

The checked-in DT-014 evidence records the same fields for each representative pair, plus
`precheck_result`, `shortest_path_invoked`, `edge_count`, `network_distance_m`, and `http_status`.
It records counted totals of 816 and 840 and includes fixtures for counted-component success and
profile mismatch without search. For each profile it also publishes the deterministic inventory and
count of graph nodes absent from `V_p`, plus the count of eligible searchable unit endpoints anchored
to those nodes. The inventory identifies each node by its canonical `anchor_node` and isolated
`reachability_id`, ordered by canonical node bytes. For the accepted artifact, the `elevator_only`
values are three isolated graph nodes and zero anchored eligible searchable unit endpoints.

An accepted-artifact profile-isolated same-anchor zero-edge route fixture is required only when at
least one actual eligible searchable unit endpoint anchors to a profile-isolated node. When that
endpoint-anchor count is zero, the inventory and zero count are the required artifact evidence and
no endpoint or fixture may be fabricated. Synthetic unit tests remain required for isolated
same-anchor zero-edge semantics and distinct-reachability precheck failures. Evidence is
canonicalized with the same RFC 8785 JSON rule; its published SHA-256 is computed over the evidence
document with any self-hash field omitted.

## Consequences

- ADR-0005's measured 816/840 baseline remains stable and comparable.
- Every eligible endpoint has a non-null, profile-scoped identity suitable for a constant-time
  precheck, including nodes excluded from a profile's edge-induced graph.
- A same-anchor request has deterministic zero-edge semantics without manufacturing connectivity.
- Distinct isolated or connected identities fail explicitly before search, and elevator-only
  failures retain the full stairs-excluded and `not_verified` disclosure.
- Accepted-artifact evidence distinguishes isolated topology from endpoint-backed route coverage;
  a fixture is conditional on an actual eligible endpoint relationship.
- Catalog and response schemas must distinguish nullable counted membership from non-null query
  reachability; implementations and tests written directly from ADR-0008 §4 require correction.

This ADR is an accepted corrective refinement to ADR-0008 §4. It supersedes only ADR-0008's use of
profile component IDs as the universal endpoint precheck identity. It retains ADR-0008's artifact
selection and non-traversal approximate-anchor decision as a bounded DT-014 PoC exception to the
future unit-connector invariant in system design §3.3 step 5. Those approximate anchors add no
connector geometry or graph edges and do not establish full product compliance. This ADR does not
supersede ADR-0005, ADR-0004 node identity, ADR-0006 lineage/container boundaries, or the read-only
source boundary.
