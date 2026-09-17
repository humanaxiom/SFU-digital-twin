# 13. Route availability choices

DT-024 planning scope note (2026-09-17): [ADR-0017](0017-navigation-state-and-journey.md) supersedes native destination-catalog presentation with searchable draft endpoint controls for the planned overhaul. Directed availability, complete outcome categories, unsupported selections and manual request fallback remain applicable. The API below is unchanged; the planned interaction model is not yet implemented.

Status: accepted for DT-020 implementation, 2026-09-11.

The route UI offers every room although most room pairs in the accepted graph are
disconnected. Show graph-supported destination choices without changing route
calculation, endpoints, graph geometry or source data.

## Read-only contract

`GET /demo/v1/route-options?origin_unit_id=<full-unit-id>&profile=<profile>` accepts
exactly one origin and one `default` or `elevator_only` profile. Reject duplicate,
missing and unknown parameters, invalid IDs/profiles, unknown origins and absent
routing capability. An ineligible origin returns 422 `endpoint_unavailable`.

A successful response has:

```json
{
  "version": "route-options-v1",
  "status": 200,
  "origin_unit_id": "...",
  "profile": "default",
  "availability_basis": "directed_profile_graph",
  "destinations": [{"unit_id": "...", "availability": "connected"}],
  "counts": {"connected": 0, "same_anchor": 0, "disconnected": 0, "endpoint_unavailable": 0},
  "provenance": {},
  "warnings": []
}
```

Exclude the origin itself and sort destinations by unit ID. Classify every remaining
catalog endpoint as `connected`, `same_anchor`, `disconnected` or `endpoint_unavailable`.
Use one directed traversal over the selected profile's allowed edges, not weak
component equality: arbitrary directed fixtures may not share the accepted graph's
bidirectionality. A distinct eligible endpoint at the same anchor is `same_anchor`,
even if that node is isolated in the profile. No walking segment is represented.

Connectivity does not certify guidance geometry, door traversal or accessibility.
Retain provenance and warnings. The actual route request remains authoritative;
this endpoint does not run A* for every destination or create connection edges.

## Client behavior

Prioritize connected destinations with clear group labels and a visible count.
Keep unsupported selections and explanations; never substitute a destination or
silently change profile. Distinguish same-anchor rooms from routes with a drawn path.
Keep manual routing usable when availability fails. All entry points (form, map,
assistant, swap, profile change, Clear) invalidate stale availability consistently;
only the latest origin/profile response may affect choices. Preserve the full room
catalog so unsupported requests remain possible and truthful.

DT-022 clarification: when one to five connected destinations exist, expose their
room/floor names as explicit direction actions rather than only a count. A click
sets that destination and uses the existing route-request flow; do not auto-select
or silently change profiles. Clear old actions when availability becomes pending,
empty or failed; apply the same generation guards to action rendering. Clearing a
previous route must also clear its failure text before a new origin is selected.

## Verification

Docker tests cover directed asymmetry, profiles, ineligible endpoints, isolated
shared anchors, exact counts, validation and stale requests. Fresh browser/API E2E
must select a connected option, verify the resulting path, retain an unsupported
selection/failure, change profile, and exercise mobile plus existing route fixtures.
Reproduce the user's exact pair if supplied; do not treat example success as repair
of disconnected source geometry.
