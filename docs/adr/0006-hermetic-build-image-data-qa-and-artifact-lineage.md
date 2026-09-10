# 6. Hermetic build image, data-QA gate, and artifact lineage

Status: accepted
Date: 2026-09-01

## Context

DT-007 exposes three build-boundary gaps that must be resolved before implementation continues:

1. [docs/DOD.md](../DOD.md) requires `make dataqa`, but the target does not exist. Earlier tickets
   reported data-QA results from ticket-specific test classes and ad hoc scripts under the ignored
   `build/` directory, so a clean checkout has no single reproducible gate.
2. The current `Makefile` runs `apt-get` and `pip install` inside gate and ETL targets. That makes
   execution depend on live Debian and Python package indexes after the container image is pulled,
   contrary to the repository's no-local-Python and reproducibility rules. ADR-0002 selected base
   images and container-only execution, but did not prohibit runtime package installation.
3. [docs/02-system-design.md](../02-system-design.md) says every artifact carries the source GDB
   hash. DT-007 is an artifact-to-artifact transform and must not mount or read the source GDB;
   DT-009 owns the final build report. Requiring DT-007 to compute the source hash would violate the
   least-privilege component boundary and its ticket scope.

DT-007 also confirms a measured contraction baseline of 7,450 nodes and 19,884 directed arcs, not
the earlier estimate of a graph in the low thousands. The protected topology and destination
attachment nodes, not a compression target, control contraction.

The source GDB remains read-only. Python, GDAL, package installation, ETL, tests, and data-QA remain
container-only. The deterministic core and the elevator-only, stairs-excluded accessibility
contract are unchanged.

## Decision

### 1. Publish one pinned build image; install nothing at target runtime

Add a checked-in `infra/Dockerfile.build` that installs the GDAL runtime, the package's locked
runtime dependencies, and gate tools (`pytest`, coverage, Ruff, and Pyright). Dependency versions
and hashes are checked in. The image build is the only step allowed to contact operating-system or
Python package repositories.

A controlled image-publish workflow builds that Dockerfile, runs its smoke checks, pushes it to the
project registry, and records the resulting immutable digest in `infra/docker-compose.yml`. Normal
developer, ETL, and gate targets use only:

```yaml
image: ghcr.io/<sfu-project>/wayfinding-build@sha256:<published-digest>
```

Compose must not define a `build:` fallback for normal execution. After the digest-pinned image has
been pulled or preloaded, `make test`, `make lint`, `make type`, `make dataqa`, and DT-007's
`make etl-graph-contract` perform no `apt`, `pip`, `uv`, or other network installation. Source code
is mounted from the checkout and imported through `PYTHONPATH`; it is not installed at target
runtime.

Use this one GDAL-capable build image for Phase 1 gates and ETL. A second Python-only image would
duplicate lock and publication work without creating a deployment boundary. Runtime API images may
split later under a separate ADR.

### 2. Separate source-capable and artifact-only compose services

Compose defines two capabilities from the same pinned image:

- `source-etl` mounts `/data/IndoorWayfinding.gdb:ro` and `build/:rw`. Only extraction and the
  DT-009 final source-lineage report may use it.
- `artifact` mounts the repository and `build/:rw`, but has no source GDB mount. Normalisation,
  graph construction, contraction, tests, lint, type checking, and artifact data-QA use it.

`etl-graph-contract` and `dataqa` must run on `artifact`. Absence of `/data/IndoorWayfinding.gdb` is
part of their contract, not merely a convention. The Docker socket is not mounted into either
service.

This is least privilege without weakening the read-only rule: the few components that need source
data receive a read-only mount; all others receive no source capability at all.

### 3. Make `dataqa` a durable artifact gate

`make dataqa` is a thin wrapper around a single `docker compose run --rm artifact ...` command. It
runs all pytest tests marked `dataqa` under `packages/wayfinding/tests`, with strict marker
validation and normal non-zero failure behavior. No ticket argument is required: the gate validates
all checked-in data-QA contracts whose prerequisite artifacts are part of the current Phase 1
build. A clean suite with no collected `dataqa` tests is a failure, not a pass.

Ticket-specific data invariants belong in tests carrying the `dataqa` marker. DT-007's marked set
must validate at least the measured node/arc counts, transition preservation, protected-node counts,
profile component counts, shortest-path equivalence, output schema, immediate-input lineage, and
absence of source-GDB access. Tests of extraction against the source GDB use a separate
`source_dataqa` marker and source-capable target; they are not silently included in the artifact-only
`make dataqa` gate.

### 4. Record immediate artifact lineage at each intermediate stage

Intermediate stats sidecars do not carry or recompute the source GDB hash. Each stage records the
artifacts it actually consumed and emitted:

```json
{
  "lineage": {
    "inputs": [
      {"path": "build/graph_with_transitions.pkl", "sha256": "..."},
      {"path": "build/wayfinding.gpkg", "sha256": "..."}
    ],
    "outputs": [
      {"path": "build/graph_contracted.pkl", "sha256": "..."}
    ]
  }
}
```

Paths are repository-relative and hashes are lowercase SHA-256 hex digests of file bytes. Inputs
are sorted by path before serialization. A sidecar does not include its own hash. DT-007 therefore
hashes only `graph_with_transitions.pkl`, `wayfinding.gpkg`, and `graph_contracted.pkl`; it neither
mounts nor reads the source GDB.

DT-009 produces the final `docs/reports/build-report.json`. It verifies the immediate-input chain,
lists hashes for the final and material intermediate artifacts, and records the source GDB directory
hash. The directory hash is deterministic: sort all regular files by repository-independent POSIX
relative path; SHA-256 each file's bytes; then SHA-256 the concatenation of each UTF-8 relative path,
a NUL byte, its lowercase file digest, and a newline. Symlinks and paths outside the mounted GDB are
rejected. The operation is read-only and runs only in `source-etl`.

This gives end-to-end provenance without granting every transform source-data access. The final
report is the authoritative mapping from source snapshot to output artifacts; intermediate
sidecars prove each local edge in that chain.

### 5. Generated artifact policy

`build/` remains ignored and disposable. Pickles, GeoPackages, temporary stats, caches, and local QA
output are regenerated through checked-in targets and are not committed. `docs/generated/` remains
reserved for the checked-in Phase 0 source-profile evidence.

Durable, reviewable summaries explicitly required by a ticket, including DT-009's final
`build-report.json`, live under `docs/reports/` and are committed. They contain hashes, counts,
versions, and validation outcomes, not binary graph or geospatial payloads. The image Dockerfile,
dependency lock, publication workflow, and resolved image digest are also checked in because they
define how ignored artifacts are reproduced.

## Consequences

### Positive

- All required gates become reproducible after one immutable image pull, with no live package
  installation and no host Python or GDAL.
- DT-007 and future artifact transforms cannot access the source GDB because it is not mounted.
- `make dataqa` becomes a stable Definition-of-Done gate rather than an informal report.
- Immediate hashes identify stale or mixed-stage inputs, while DT-009 provides complete source to
  output provenance once the final graph exists.
- Ignored build artifacts remain cheap to regenerate; durable evidence remains reviewable in Git.

### Negative

- The project must operate an image publication workflow and update the compose digest whenever the
  lock or Dockerfile changes.
- A newly changed dependency cannot be tested through an ad hoc runtime install; the image must be
  rebuilt, validated, and published first.
- Historical DT-005 and DT-006 sidecars lack the new lineage object. DT-009 must either regenerate
  them with the current pipeline or report them as legacy artifacts; it must not invent hashes that
  were not captured or verified.
- The single Phase 1 image is larger than a Python-only gate image because it includes GDAL.

### Supersedes

This ADR supersedes ADR-0002's container-image examples and its permission to extend gate execution
from mutable base images. ADR-0002's package layout, per-package coverage floor, container-only
execution, and read-only source boundary remain accepted.

This ADR also supersedes the sentence in system design section 3.4 that requires every intermediate
artifact to carry the source GDB hash. Immediate artifact lineage plus DT-009's final source hash is
the replacement contract.

### Independent of

ADR-0003's normalized schema, ADR-0004's graph identity and serialization decisions, and ADR-0005's
measured connectivity gates remain unchanged. The measured DT-007 contraction baseline refines the
system's capacity description but changes no graph schema or routing API.

### Required implementation work

1. `implementer`: add the locked `infra/Dockerfile.build` and controlled image-publish workflow;
   publish it and replace all compose image tags with the resulting immutable digest.
2. `implementer`: split compose into `source-etl` and `artifact`, remove the Docker socket mount,
   and rewrite every Make target to invoke preinstalled tools without `apt` or `pip`.
3. `implementer`: add `.PHONY` targets `dataqa` and `dataqa-source`; run DT-007 contraction and the
   required gates on `artifact`, and extraction/final source hashing only on `source-etl`.
4. `test-writer`: register `dataqa` and `source_dataqa` markers, mark the existing invariant checks,
   and add gate tests proving zero collected QA tests fails, no runtime installer command remains,
   the image is digest-pinned, and DT-007 has no GDB mount.
5. `test-writer`: add red tests for the exact lineage schema, deterministic sorting and SHA-256
   values, stale-input detection, and the DT-009 GDB directory-hash algorithm.
6. `implementer`: add lineage generation only after those tests fail; DT-007 must hash its declared
   input/output files and must not receive a source path.
7. `planner`: make DT-009 own regeneration/verification of the lineage chain and the committed final
   `docs/reports/build-report.json`, including the source GDB directory hash.
