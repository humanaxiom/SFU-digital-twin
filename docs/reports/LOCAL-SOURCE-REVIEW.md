# Local source verification — 2026-09-11

The user confirmed that ECC, AQ and Strand Hall source files are under this
repository's ignored `data/` directory. All three geodatabases open read-only with
OpenFileGDB in Docker. Earlier extraction/source-QA skips checked the absence of
`/data/IndoorWayfinding.gdb` in artifact containers; they did not establish that
the source files were missing from the host.

## Inventory

Both `IndoorWayfinding.gdb` and `IndoorWayfinding_AQ_SH_ECC_Revised.gdb` contain:

| Facility | Source ID | Levels | Raw units | Pathways with this facility ID |
| --- | --- | ---: | ---: | ---: |
| ECC | SFU_BURNABY_ECC | 1 | 33 | 419 |
| AQ | SFU_BURNABY_QUAD | 6 | 828 | 16,675 |
| Strand Hall | SFU_BURNABY_STRAND | 4 | 349 | 5,332 |

These are raw source counts, not searchable-room or routability counts. Both
datasets also contain 55,593 details, 41 landmarks and 63 transitions (42 stairs,
21 elevators). The feature layers declare EPSG:26910 projected coordinates with
EPSG:5713 vertical coordinates in a compound CRS.

The legacy pathway layer is `Pathways_AQ_SH_ECC`, with 22,426 features. The revised
layer is named `Pathways_AQ_SH_ECC_Revised`, with 22,567 features. **141 revised
pathways have null `FACILITY_ID` and `LEVEL_ID`.** All pathway and transition
`TRAVEL_DIRECTION` values observed are 1. A separate direct OGR scan compared
pathways by source FID: all 22,426 legacy features retain identical attribute values
and raw WKB in revised; the 141 additions are FIDs 22427–22567. Their level names
are single spaces and their vertical orders are 0 (140 records) or 1 (one record).
These values do not establish their facility or floor assignments. Equal counts
in other layers do not prove equal attributes or geometry; no source-to-graph
comparison is claimed here.

`AdditionalData_Testing.gdb` contains 82 building entrances, 82 main doors and
34 ramps, plus attachment tables with 105, 120 and 37 records respectively.
Its spatial layers declare EPSG:26910 without a vertical CRS. These layers lack
the indoor layers' `FACILITY_ID`/`LEVEL_ID` fields; their `ReferenceLevel` values
and geometry require explicit reconciliation. They remain profile-only under
ADR-0008 and do not establish traversability or verified accessibility.

## Snapshot identities

Docker read every regular file and applied ADR-0006's directory hash algorithm:
sort POSIX-relative paths; hash each file; hash the concatenation of path, NUL,
lowercase file hash and newline. No source files were written.

| Local geodatabase | Files | Bytes | Directory SHA-256 |
| --- | ---: | ---: | --- |
| IndoorWayfinding.gdb | 81 | 13,430,105 | 8710ab93e5c66c8a442f8db2baa4e7efb2c77ea46006e5d301c63796c332f07e |
| IndoorWayfinding_AQ_SH_ECC_Revised.gdb | 83 | 14,119,013 | 6dcdf97d0d1a6b5f0bee4bfdd905d635bc81e43ec3c8e58b4ab772f74a42ae60 |
| AdditionalData_Testing.gdb | 100 | 896,449,110 | f141fa7a2a91bd7fcfc8ae1a6790e9d6bde0f03f240abe084e21a02f2aa564cc |

The sibling `C:/repos/sfudt/claude/dtwin-harness/data/IndoorWayfinding.gdb` has the
same directory hash, file count and byte count as local `IndoorWayfinding.gdb`.
Selecting the local legacy copy therefore preserves the input snapshot. This
does not complete the source-to-artifact lineage report deferred to DT-009.

## Container boundary finding

The old source-etl configuration selected the sibling copy. Its broad repository
bind also exposed all local sources through `/workspace/data`, writable in artifact
and source-etl and readable in demo. A read-only runtime probe in a fresh artifact
container listed all three GDBs and reported `read_only: false`; its source-absence
assertion failed. Prior checks only inspected explicit `.gdb` mounts and missed
this alternate path. The earlier assertion of artifact source exclusion was too strong.

The scoped repair selects the byte-identical local legacy input and masks
`/workspace/data` with empty read-only tmpfs in all three services. Source-etl
retains explicit read-only `/data/IndoorWayfinding.gdb` access. This restores the
existing ADR-0006 boundary without changing routing, ETL semantics or artifacts.
Already running containers retain their original mounts until recreated.

Regression evidence: the new configuration checks failed four cases before repair
(three unmasked services and the sibling source path). Fresh Docker Compose
containers after repair reported empty, read-only `/workspace/data` for artifact,
source-etl and demo. Only source-etl had `/data/IndoorWayfinding.gdb`, and that
mount reported read-only. The probes used directory enumeration and `os.statvfs`
flags, without attempted writes. All three exited 0. Source QA against the local
legacy mount passed **1 test**, exit 0; log/JUnit: `build/local-source-review/source-qa.*`.

Runtime probes used `docker compose -p sfudt-source-boundary-runtime -f
infra/docker-compose.yml -f infra/docker-compose.local.yml run --rm --no-deps -T`
with each service and Python assertions. The source check used the same files,
project `sfudt-local-source-qa`, source-etl, and
`pytest packages/wayfinding/tests/test_source_dataqa.py --no-cov -p no:cacheprovider`
with the repository's `PYTHONPATH`. No running demo or accepted artifact was changed.

Focused post-repair gates in fresh offline Compose artifact containers passed:
**90 tests, 2 skipped** (the two Docker-CLI checks), Ruff across package/tools,
launcher fixtures and the no-host-Python gate, all exit 0. The pytest selection
was `test_adr0006_hermetic_build.py`, `test_dt002_etl_infrastructure.py`,
`test_dt015_demo_deployment.py`, `test_docker_evidence.py`, and
`test_docker_hook.py`, with `--no-cov -p no:cacheprovider`. Logs including exit codes
are under `build/local-source-review/`. The earlier 468-pass full suite and browser
run predate this configuration repair; no production Python/JavaScript or accepted
artifact changed, and those suites were not repeated for this scoped mount change.

## Execution and next comparison

All data parsing and hashing used Docker containers with networking disabled,
explicit read-only source binds, and existing `wayfinding-build:local` image ID
`sha256:0b67be1d851168d326c422762b369d1ce129a9ed3c20429d5014c98ed10a4947`.
GDAL reported `3.14.0dev-17759e56cbe7d693a39c3d5ccf339364de844ee7`.
The inventory used `ogr.Open(path, 0)`, layer definitions, feature counts and
field-value counters; the identity comparison used Python SHA-256 inside Docker.
This is a source inventory, not a full topology, geometry or provenance audit.

Before revised ingestion: map the renamed pathway layer; reconcile the 141 records
without facility/level identity; compare stable pathway identities and geometry;
check weights, multipart continuity, level references and transition semantics;
then rebuild under a separate output root. Compare room-anchor eligibility and
profile-specific unit-pair reachability as well as component counts. Supplemental
entrance/door/ramp ingestion and source promotion require the decisions and lineage
evidence specified by ADR-0008. Existing image-access, CI and physical LAN acceptance
limits remain separate.

Independent large-model review found no blocking implementation or source-evidence
issue in this scoped repair. This does not approve revised ingestion or full DOD.
