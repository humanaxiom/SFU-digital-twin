---
description: "Use when writing or reviewing any script, test runner, ETL step, or gate command for this repo. Covers the no-local-Python / container-only execution rule."
applyTo: "tools/**,infra/**,Makefile,packages/**"
---
# Container-only execution

- Never install or invoke Python, GDAL, `pip`, or a database client directly on the host. This
  workspace runs everything data- or test-related inside a container — follow the pattern in
  [tools/run_profile.ps1](../../tools/run_profile.ps1), which shells out to
  `ghcr.io/osgeo/gdal:alpine-small-latest` and mounts the data directory `:ro`.
- PowerShell wrapper scripts that only parse files directly (no GDAL/Python needed —
  e.g. [tools/dump_gdb_schema.ps1](../../tools/dump_gdb_schema.ps1)) are the sole exception; they
  exist specifically because they need no runtime dependency at all.
- Once Phase 1 adds `infra/` and a `Makefile`, every gate target (`test`, `lint`, `type`, `dataqa`)
  must be a thin wrapper around `docker compose run --rm <service> <command>` — never a bare `uv
  run`/`pytest`/`python` invocation, and never assume `python`, `psql`, or `ogr2ogr` exist on the
  host.
- Any new script must be re-runnable from a clean checkout with no network access beyond pulling
  the pinned container image, and no agent present.
