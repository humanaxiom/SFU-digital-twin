# DT-023 Stage 0 — independent coverage and source audit

Date: 2026-09-11. Scope: the three-building local pilot; no source admission,
artifact promotion, building-entrance route contract, or campus-wide coverage claim.
This evidence does not approve delivery; the lead's integrated Docker/browser/API
E2E and judgment remain required.

The reproducible read-only audit is `tools/dt023_gis_audit.py`. It loads the trusted
accepted artifacts and the unpromoted `dt022-exact-final3` candidate through the
existing artifact hash checks. It measures **directed** reachability, rather than
equating weak-component membership with routing. Parallel graph arcs are retained
in the input; pair counting counts endpoint pairs, not alternative arc paths.
Distinct rooms sharing one approximate anchor count as reachable, separately from
connected distinct-anchor pairs; a room paired with itself is excluded. The four
ADR-0016 buckets (`connected`, `same_anchor`, `disconnected`,
`endpoint_unavailable`) partition every row's ordered-pair total. No room-to-anchor
connector is constructed or validated.

## Ordered building-pair matrix

Every row is an ordered origin → destination pair. The two profile columns show
default / elevator-only reachable room-pair counts. Catalog and eligible room
counts are AQ 686, ECC 18 and Strand 313 in both artifact sets. Facility identities
are `SFU_BURNABY_QUAD`, `SFU_BURNABY_ECC` and `SFU_BURNABY_STRAND`, read directly
from `facility_26910` and joined through the exact `level_26910` relationship.
No identifier prefix is parsed or inferred. These IDs do not constitute a complete
Burnaby inventory. The table's reachable counts include both `connected` and
`same_anchor`; the evidence JSON retains the separate buckets.

| Origin → destination | Eligible ordered pairs | Accepted default / elevator-only | Candidate default / elevator-only |
| --- | ---: | ---: | ---: |
| AQ → AQ | 469,910 | 62,108 / 54,876 | 468,540 / 468,540 |
| AQ → ECC | 12,348 | 0 / 0 | 8,220 / 8,220 |
| AQ → Strand | 214,718 | 0 / 0 | 0 / 0 |
| ECC → AQ | 12,348 | 0 / 0 | 8,220 / 8,220 |
| ECC → ECC | 306 | 130 / 130 | 162 / 162 |
| ECC → Strand | 5,634 | 0 / 0 | 0 / 0 |
| Strand → AQ | 214,718 | 0 / 0 | 0 / 0 |
| Strand → ECC | 5,634 | 0 / 0 | 0 / 0 |
| Strand → Strand | 97,656 | 4,484 / 3,722 | 95,796 / 34,298 |

`endpoint_unavailable` is zero in every measured row. Same-anchor counts occur
only on the AQ diagonal (accepted 50, candidate 48) and Strand diagonal (8 in
both); these values are the same in both profiles. All other same-anchor counts
are zero. Thus the table's reachable value minus the stated same-anchor count
gives `connected`, and total minus reachable gives `disconnected`. The JSON
records these four exact counts explicitly for all 36 snapshot/profile/pair rows.

Rows with connected distinct-anchor pairs have ADR-0016 status **mapped_route**,
strictly meaning at least one indoor-graph path. Their building coverage remains
partial, since other room pairs remain unsupported and entrances are unverified.
All zero rows here are
**disconnected**, with eligible room endpoints present. Buildings outside the pilot
are **unavailable** because this dataset contains neither their identity/footprints
nor routable endpoints. No row warrants full-building or verified-entrance routing
status. Elevator-only continues to mean stairs excluded, not verified accessibility.

The candidate's 8,220 AQ/ECC pairs occur in **each direction**, not a combined
16,440 unordered count. Example graph-backed pair in both profiles:
`SFU_BURNABY_QUAD_1000_1001` → `SFU_BURNABY_ECC_3000_3176` (and reverse).
This is graph reachability evidence, not proof of an authored portal or a new
outdoor journey. Existing DT-022 candidate evaluation remains separate historical
route/browser evidence; this audit does not promote that candidate.

## Independent revised-source observations

Reading `IndoorWayfinding_AQ_SH_ECC_Revised.gdb` directly with GDAL, read-only,
confirms 141 added features (22427–22567), all single-part, totaling
12,800.799684135807 m by their stored `LENGTH_3D`. All 141 lack facility and level
IDs; vertical order is 0 for 140 and 1 for one; 134 have at least one Z=0 vertex.
The layer declares NAD83 / UTM zone 10N (EPSG:26910) and CGVD28 height (EPSG:5713).
That CRS declaration does not establish whether zero elevation means measured
ground, a local floor datum, or missing data.

Exact added-line endpoint contacts with existing pathway vertices are:

| Added FID | Existing pathway FIDs | Existing recorded level(s) |
| ---: | --- | --- |
| 22429 | 9436, 17983 | Strand 1000 |
| 22452 | 18619 | Strand 2000 |
| 22471 | 9328, 9347 | AQ 3000 |
| 22473 | 919 | AQ 2000 |
| 22497 | 5118, 12825 | AQ 3000 |
| 22498 | 3289, 5114 | AQ 3000 |
| 22534 | 14826 | AQ 4000 |
| 22540 | 919 | AQ 2000 |
| 22562 | 5150; 11921 | AQ 3000; AQ 2000 |

FID22562 demonstrates why XYZ coincidence cannot supply missing level semantics:
the same endpoint coincides with existing vertices assigned to **two different
AQ levels**. The audit records full native XYZ and source FIDs in JSON; it uses
no rounding, snapping, intersections, proximity thresholds, or invented edges.

Consecutive source vertices of only the additions form 43 literal undirected
XYZ components. The largest has 659 vertices and contacts AQ3000 FIDs
3289/5114/5118/12825 and Strand2000 FID18619. This independently reproduces the
AQ–Strand geometric lead. The intentionally literal component ignores missing
grade, access, direction, and portal semantics and is **excluded from routing**.
The nine endpoint matches are investigation candidates, not nine admitted portals.

## Scope and reconciliation decision

Stage 1 may expose the three existing facility footprints with explicit partial
indoor coverage, their real local floor labels, and the current graph's limitations.
The unknown wider inventory must remain explicit. Retain accepted artifacts as the
default; maintain exact-source topology only as the already isolated ADR-0015
candidate. Do not silently include the 141 additions or supplemental entrances,
doors, and ramps excluded by ADR-0008.

DT-017's multipart repair remains separate: DT-022 explicitly excludes 12 inherited
multipart and six self-loop features from exact noding, and skips 85 unsafe
junctions. This audit does not revalidate or repair those 18 exclusions. Their
existing representation is not grounds to admit additional geometry. Independent
classification, same-grade junction decisions, stable entrance/door/path joins,
public access/direction, and source authority are still needed for Stage 2.

## Execution and verification

All execution used local development image `wayfinding-build:local`, image ID
`sha256:0b67be1d851168d326c422762b369d1ce129a9ed3c20429d5014c98ed10a4947`.
This does not certify the published immutable default image. No accepted artifact
or source file is written. The audit output is created exclusively under
`build/dt023-gis/`; a repeated filename fails rather than overwrites evidence.

```powershell
docker run --rm --name dt023-gis-audit-final3 --network none --mount 'type=bind,source=C:/repos/sfudt/ghcp,target=/workspace' --tmpfs /workspace/data:ro,noexec,nosuid,size=1m --mount 'type=bind,source=C:/repos/sfudt/ghcp/data/IndoorWayfinding_AQ_SH_ECC_Revised.gdb,target=/source.gdb,readonly' -e PYTHONPATH=/workspace/packages/wayfinding/src -w /workspace wayfinding-build:local python tools/dt023_gis_audit.py --output build/dt023-gis/audit-final3.json
docker compose -p dt023-gis-check -f infra/docker-compose.yml -f infra/docker-compose.local.yml run --rm -T -e PYTHONPATH=/workspace/packages/wayfinding/src artifact python -m pytest packages/wayfinding/tests/test_dt023_gis_audit.py --no-cov -q
docker compose -p dt023-gis-check -f infra/docker-compose.yml -f infra/docker-compose.local.yml run --rm -T artifact ruff check tools/dt023_gis_audit.py packages/wayfinding/tests/test_dt023_gis_audit.py
```

The synthetic oracle covers one-way direction, parallel arcs, stairs exclusion,
same-anchor distinct rooms and unavailable endpoints. It was added after initial
audit implementation (not a retroactive test-first claim), then exposed a real
classification failure: zero eligible pairs were labelled disconnected. That RED
exited 1. Subsequent ADR-0016 review required a more precise four-bucket partition,
opaque level-ID joins and a zero-room building. Its expanded test failed before
the new crosswalk was implemented, then passed after implementation (1 passed,
0 skips). The final semantics classify unavailable-only/same-anchor-only source
coverage as partial and absent endpoint catalogs as unavailable. Ruff exited 0.
An earlier test command omitted `PYTHONPATH` and failed
import; that setup error is not the behavioral RED. An initial GDAL discovery
command mounted the GDB without a `.gdb` suffix and failed; retry with
`/source.gdb` succeeded. The initial audit invocation exited 0; final output
identities and timestamp are recorded below after the final rerun.

Final audit exited **0** after application freeze; report timestamp is
**2026-09-12 02:55:05 UTC**. Evidence: `build/dt023-gis/audit-final3.json`, SHA-256
`75f64b6f41214e65a7861c5a386cf3a0846d1e2749cd897fa52a02af3c0af76e`.
It includes per-file source hashes, the audit script and all application Python
module hashes, full source contact records, candidate status and both exact
artifact identities. These code hashes exclude static JavaScript and browser
fixtures; their validation belongs to the lead's browser/gate evidence. Earlier
`audit.json`, `audit-final.json` and `audit-final2.json` are superseded. A Docker
comparison exited 0 confirming final2/final3 artifact identities, directed
partitions and complete source audit are identical. The audit script and application
Python modules were unchanged afterward. Later browser-fixture corrections and their
fresh runs are recorded separately in `DT-023.md`.

| Artifact | Accepted SHA-256 | Candidate SHA-256 |
| --- | --- | --- |
| GeoPackage | `f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65` | `baf80690197f1fb00e2eca58eb3c0835ae9f9b65667da843a683679d5f240eb9` |
| Contracted graph | `ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d` | `93c2ff2994e6e564adecae3506175f2c0047948e1d84e44045d2c70267071d46` |
| Graph stats | `2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1` | `e70b32760caded0f47b461530f335a41d6cee018bb34ad1dbdbc1f56ba77173a` |
