# 11. Isolated source review and legacy rebuild

Status: accepted for DT-016 implementation
Date: 2026-09-11

## Context

The user authorized building from the current handoff and improving the plan.
The local legacy source is verified, but revised adds 141 pathways without facility
or level IDs. Existing stage entry points overwrite accepted `build/` outputs, and
`make etl` does no work. One-off source inspection cannot support repeatable comparison.

## Decision

Introduce a Docker-only source-review command and an isolated legacy rebuild command.
The legacy builder accepts only source directory hash
`8710ab93e5c66c8a442f8db2baa4e7efb2c77ea46006e5d301c63796c332f07e`.
This binds existing normalization/provenance assumptions to the reviewed snapshot;
it does not claim they generalize to future sources. Other snapshots fail closed.
Source review remains a separate quality result: eleven legacy multipart pathways
have noncontiguous stored part order. This baseline builder reproduces existing
behavior for comparison. A complete run means verified reconstruction/lineage;
it does not mean source quality passed or permit promotion. DT-017 will address
multipart ordering before changing accepted geometry or connectivity.

Separate capabilities share read-only code and a writable `build/experiments/` mount:

- source-review reads all three local GDBs read-only and writes diagnostic reports;
- source-build reads only the legacy GDB for extraction and final source verification;
- artifact-build sees no raw GDB and performs normalization, graph stages and comparison.

All use disabled networking and mask `/workspace/data`. They do not mount the Docker
socket or publish ports. Accepted artifacts are visible read-only through the code
workspace. Existing running stacks are not repurposed.

Each run ID is a conservative ASCII basename and creates an exclusive directory.
No overwrite, resume or automatic promotion is provided. Reject symlink paths and
escapes from the fixed experiments root. Preserve raw extraction separately from
the working normalized GeoPackage. Before every dependent stage, verify its state,
toolchain/code identity and input hashes; record the consumed inputs and produced
outputs. Finalization rechecks all retained artifacts and source identity before
marking a candidate complete. Failures remain visibly incomplete.

The new run manifest uses paths relative to its run directory, explicitly recorded
as `path_base: run_directory`. It supplements the existing contraction sidecar;
the sidecar retains its legacy parent-relative path convention for nested outputs.
The manifest validates its exact input/output hash entries and does not rely on
suffix-only path matching. This is an experimental lineage format, not DT-009's
production source-to-artifact promotion report.

Source comparison maps the seven layer names explicitly and compares source-FID
records by schema, attributes and raw WKB. FID correspondence is evidence for these
snapshots, not a general stable identity guarantee. Missing identities, unsupported
directions, invalid weights/coordinates or disjoint multipart geometry are reported
as ingestion blockers. No source correction or inferred connectivity is performed.
Supplemental layers remain inventory-only under ADR-0008.

Semantic comparison canonicalizes graph metadata, all nodes and directed multiedges,
attributes and ordered geometry coordinates without rounding. It includes units,
approximate room anchors and profile-specific room reachability. Reject unsupported
or nonfinite values; validate bidirectional topology before using component groups
as exact reachability. Preserve parallel edges and profile-isolated same-anchor pairs.
Report byte hashes independently because GeoPackage metadata and pickle ordering can
differ while graph behavior remains equal. Equal semantic signatures do not certify
the physical accuracy or accessibility of the source.

## Consequences

`make etl` becomes a safe full isolated legacy build with an explicit run ID; legacy
individual stage targets remain available with their existing behavior. New commands
give a reproducible baseline and actionable revised-source diagnostics while leaving
source promotion, supplemental ingestion, image publication and LAN acceptance open.
No revised eligible-subset graph is presented as a complete revised build.
