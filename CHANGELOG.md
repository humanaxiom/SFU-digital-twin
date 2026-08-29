# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `packages/wayfinding/` Python package skeleton with `pyproject.toml`, `src/wayfinding/`, and `tests/` directory structure ([DT-001](docs/plans/DT-001.md))
- `infra/docker-compose.yml` defining a containerized `test` service with GDAL support, mounting the package read-write and the source geodatabase read-only ([DT-001](docs/plans/DT-001.md))
- `Makefile` with `test`, `lint`, and `type` gates wrapping `docker compose run --rm test` commands to enforce container-only execution ([DT-001](docs/plans/DT-001.md))
- ADR-0002 documenting package layout convention, per-package coverage floors, container execution model, and the read-only mount rule for the source GDB ([DT-001](docs/plans/DT-001.md))
- Coverage floor of 85% line coverage for `packages/wayfinding` in `docs/DOD.md` ([DT-001](docs/plans/DT-001.md))
- Gate smoke tests in `tests/gate/` to verify no local Python execution and read-only GDB mount ([DT-001](docs/plans/DT-001.md))
