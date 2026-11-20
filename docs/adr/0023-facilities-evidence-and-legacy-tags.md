# 23. Facilities evidence and legacy accessibility tags

Status: Accepted
Date: 2026-11-19

## Context

Facilities reports automatic-door locations, but no door-width or elevator-dimension
survey. Facilities cannot supply a closure or elevator-outage feed; whether
Security has a suitable feed is unknown. Restrictions would therefore need manual
maintenance under the currently known evidence. Building IDs, names, acronyms and room IDs are
authoritative; aliases are supplemental. No walking-speed or elevator-wait
standards were supplied. Current building/room schemas are consistent, while the
availability, schema and scope of future exports remain unclear.

ADR-0003 preserved category-derived `accessible` flags with `verified_by` and
`verified_date` fields. `source_gdb_use_type` identifies a mapping source, and its
date comes from source metadata, not an accessibility inspection. A category rule
can also derive false without an explicit negative assertion in the source.
The previous room-details labels could imply stronger verification than exists.

## Decision

### Immediate display containment

Retain existing immutable artifacts, ETL mapping and API fields for compatibility.
Omit the raw flag and verification rows from room details. Where retained in the
API or interpreted in future work, the flag is a category-derived value, with
unknown remaining unknown. Never translate a derived false into “source says not accessible”.
Source-recorded use-type text may remain visible as such, including an accessible
washroom classification, but it is not evidence of audited usability.

Interpret retained `verified_by` and `verified_date` as legacy provenance/source
metadata, not verification of physical accessibility. Any future presentation
must preserve that distinction. State explicitly in room details that destination
accessibility is unverified. Neither populated metadata nor a true flag establishes
door width, usable elevator dimensions, present operational status or route access.

This supersedes ADR-0003's interpretation of a true flag as confirmed room
suitability, and any implication that its source-derived date is an audit date.
It refines ADR-0007's source-tag display contract without changing response keys.
ADR-0008's elevator-only, stairs-excluded routing and approximate same-level room
anchors remain unchanged. No source rebuild, artifact promotion, connector or
route-policy change is authorized by this decision.

### Requirements for later phases

These are admission requirements, not assertions that the capabilities exist:

- Preserve authoritative IDs, names, acronyms and room IDs. Curated aliases must
  retain their source and resolve ambiguity explicitly; they cannot silently
  replace canonical identity.
- Automatic-door locations are informational evidence only. Before integrating
  supplemental door/entrance/ramp features, accept a schema, exact level/entity
  mapping and provenance contract. Location does not establish a usable passage,
  operating power assistance, or a traversable room-to-path connector.
- Separate source assertions and derived classifications from actual verification
  in any future schema/API. Verification requires recorded observation, scope,
  method, responsible verifier and observation date; stronger accessibility
  claims require the relevant dimensions and physical traversal evidence.
- Manual restrictions require an accepted overlay contract with stable affected
  entity/edge identities, provenance, responsible owner, effective dates and
  review/expiry behavior. Expose freshness and coverage limitations. Absence or
  expiry of a restriction must not be presented as proof that a route is open.
  Define deterministic routing effects and stale-data policy before implementation;
  do not imply an authoritative live feed.
- Travel-time estimates remain unavailable until an explicit assumptions and
  calibration contract is accepted. Do not invent institutional timing standards.
- Admit future extracts through schema and identity validation, isolated build,
  geometry/reachability comparison and reviewed promotion. A consistent schema
  today does not establish future coverage, availability or physical correctness.

DT-017 source/geometry reconciliation remains a separate prerequisite for affected
source ingestion. Supplemental data remains profile-only under ADR-0008 until its
own admission decision. All inputs remain immutable.

## Verification and consequences

The immediate increment needs regression coverage for true, false and unknown
flags, populated and missing provenance, and source use-type text. A fresh Docker
browser/API run must exercise room-details display and existing route behavior
after final runnable assembly. No source pipeline run is required for this
display-only increment because source, build code and artifacts are unchanged.

The retained API names remain historical and potentially misleading to independent
consumers. This decision documents their limited meaning; it does not silently
migrate their schema or claim to solve that future compatibility work.
