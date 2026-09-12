---
description: "Use when writing or reviewing project code, scripts, tests, builds, ETL, gates, or evidence generation for this repo. Covers the Docker-only execution rule."
applyTo: "tools/**,infra/**,Makefile,packages/**"
---
# Docker-only execution

- All project code, scripts, tests, builds, data processing, and evidence or hash
  generation must run inside Docker. The host may only inspect or edit repository
  files, invoke Git or Docker CLI commands, and run thin launcher glue that starts
  Docker. This applies to every agent tier.
- Never install or invoke Python, GDAL, `pip`, a database client, a test runner, a
  project module, a data parser, or an evidence/hash script directly on the host.
  The direct-file PowerShell parser exception is removed. Data/artifact parsing and
  hashing belong in a container; ordinary repository inspection/editing remains allowed.
- Every gate and build target must be a thin wrapper around `docker compose run
  --rm <service> <command>` (or an equivalent Docker invocation). Never use a bare
  `uv run`, `pytest`, `python`, `psql`, or `ogr2ogr` invocation on the host.
- If Docker or the required image is unavailable, stop execution and report the
  blocker. Do not use a host-runtime fallback.
- New scripts must be re-runnable from a clean checkout with no network access
  beyond pulling the pinned container image, and with no agent present.
