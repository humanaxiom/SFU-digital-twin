# 15. Experimental exact source-vertex junctions

Status: superseded for new-build defaults by ADR-0018, 2026-09-23. The experimental
evidence and endpoint-mode comparison contract remain historical.

## Evidence

AQ6071 currently reaches only AQ6067. Authoritative legacy FID16548 starts at
the exact XYZ coordinate of an interior vertex in FID9166, on the same AQ6000
level. FID16543→9166 and FID16551→9168 provide further examples. These single-part
features match the revised source. Endpoint-only graph construction omits these
source junctions. This is separate from DT-017's multipart ordering defect.

## Explicit experimental mode

Keep `endpoint-v1` as the default builder behavior. Add opt-in
`exact-shared-vertices-v1`, selected by `extract --topology` and sealed in
`build_config.topology_mode` in the run manifest. Derive and finalize consume that
configuration; environment variables cannot change it between stages. Preserve
same-build code, image, source and stage-ledger verification. Compare two fresh
variants built from the same final code, without weakening fingerprint checks.

In exact mode, split single-part pathways only at existing source XYZ vertices
shared with distinct pathways on the same recorded level, or exact transition
endpoints assigned to that level. Never interpolate an intersection or bridge a
gap. Never infer level assignment from spatial proximity. Multipart pathways are
excluded from this noding change and explicitly audited; DT-017 remains open.

Skip proposed junctions whose snapped 1cm cell collides with incompatible native
XYZ or level identities, and record why. Do not create a false connection through
rounding. Existing endpoint-mode collision behavior is a disclosed baseline, not
a reason to introduce additional proximity connections.

Preserve original coordinate sequences and every represented source segment.
Allocate the authoritative feature LENGTH_3D across split spans in proportion to
their native 3D lengths, conserving the feature total; reject invalid/nonpositive
metrics for a proposed split. Do not replace authoritative weights with geometry
lengths or hide pre-existing metric disagreement.

Preserve original PW/TR start/end node-map entries and add indexed vertex entries
for new cuts. Split physical feature identifiers must be unique so contraction
does not collapse distinct spans. Retain real source FIDs separately and ordered
source vertex spans through contraction, including reversed direction. Preserve
parallel edges. Include a hashed topology audit in the exact-mode stage ledger.

## Delivery boundary

No source edits or automatic accepted-artifact replacement. Build an endpoint
baseline and exact-vertex candidate in distinct new experiment directories. Report
gained/lost profile-specific room connectivity, exact source provenance, geometry
and cost conservation, collision exclusions and unresolved data limits. Serve the
candidate in a separate local demo for review and test it end to end against the
actual candidate. Historical accepted-artifact fixtures cannot certify it.

Require RED/GREEN source-junction, elevation/level separation, false snapped-cell
collision, reverse/parallel edge, conservation and manifest-drift tests. Final
source-to-candidate reconstruction, full gates and real browser/API checks must
pass before a scoped implementation judgment. Candidate usefulness and remaining
limitations must be stated separately from mechanical test success.
