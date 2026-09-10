# Definition of Done

A ticket is Done when ALL of the following hold:

1. A plan exists under `docs/plans/<ticket-id>.md` and every acceptance criterion is met, or has a
   `judge`-accepted deviation note.
2. Tests were committed before implementation (visible in history); the full suite is green;
   coverage is at or above the per-package floor (to be fixed in the Phase 1 ADR that introduces
   `packages/` — this file is updated then, not before).
3. `make test`, `make lint`, `make type`, `make dataqa` all pass. `make dataqa` is the
   artifact-only, containerized pytest marker gate defined by ADR-0006; collecting no `dataqa` tests
   is a failure. Source-reading QA is explicit and separate.
4. No new external network dependency; no personal or user data leaves SFU-controlled
   infrastructure. After the digest-pinned build image is pulled or preloaded, gates and ETL targets
   perform no package installation or other network access.
5. Accessibility-affecting data or logic carries provenance (`verified_by`, `verified_date`) and a
   conservative default (unknown != accessible) — see
   [.github/instructions/accessibility-claims.instructions.md](../.github/instructions/accessibility-claims.instructions.md).
6. Migrations (once they exist) are reversible and tested — upgrade and downgrade both exercised.
7. Every state-changing action the ticket depended on (imports, migrations, fixture/golden capture,
   data transforms) is a script or Makefile/compose target checked into the repo — never a one-off
   command run in a session. A fresh checkout with the pinned image and required read-only source or
   upstream artifacts preloaded must be able to run the scripts and rebuild the affected artifact
   without network access or an agent.
8. `judge` verdict `APPROVE` is recorded in the PR/commit description.
9. `CHANGELOG.md` and affected README/docstrings are updated by `doc-writer`.

## Coverage floors

Per-package coverage floors (line coverage), not blended across the workspace. Set by ADR-0002.

- **packages/wayfinding**: 85% line coverage

This floor is enforced in the package's `pyproject.toml` via `pytest --cov-fail-under=85` and in
the `make test` gate. Coverage is measured over `packages/wayfinding/src` only (excludes tests).
