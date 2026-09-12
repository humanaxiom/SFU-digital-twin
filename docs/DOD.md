# Definition of Done

A ticket is Done when ALL of the following hold:

0. All project code, scripts, tests, builds, data processing, and evidence or hash
   generation used by the ticket run inside Docker. The host is limited to repository
   inspection/editing, Git and Docker CLI operations, and thin Docker launcher glue;
   this applies to every agent tier. Host test runners, direct data parsers, and
   host evidence/hash processing are prohibited. If Docker is unavailable, execution
   stops rather than falling back to a host runtime.

1. A plan exists under `docs/plans/<ticket-id>.md` and every acceptance criterion is met, or has a
   `judge`-accepted deviation note.
2. Relevant behavioral tests failed before implementation (record RED evidence; preserve test-first
   commits where practical without committing inherited unrelated work); the full suite is green;
   coverage is at or above the per-package floor listed below.
3. `make test`, `make lint`, `make type`, `make dataqa` all pass. `make dataqa` is the
   artifact-only, containerized pytest marker gate defined by ADR-0006; collecting no `dataqa` tests
   is a failure. Source-reading QA is explicit and separate. These gates alone never establish
   completion.
4. Every green, complete, or ready judgment has a fresh Docker end-to-end run for that delivery,
   after the final runnable code, configuration, and artifacts are assembled; this includes small
   and docs-only changes. The E2E scope exercises the changed workflow; application delivery
   includes real demo browser checks and API route checks with recorded fixtures and coverage, and source or
   build changes include source-to-candidate pipeline verification. Any failed or unrun required
   E2E means the ticket is incomplete. Recording the run's evidence afterward does not change the
   runnable state or require a second run.
5. No new external network dependency; no personal or user data leaves SFU-controlled
   infrastructure. After the digest-pinned build image is pulled or preloaded, gates and ETL targets
   perform no package installation or other network access.
6. Accessibility-affecting data or logic carries provenance (`verified_by`, `verified_date`) and a
   conservative default (unknown != accessible) — see
   [.github/instructions/accessibility-claims.instructions.md](../.github/instructions/accessibility-claims.instructions.md).
7. Migrations (once they exist) are reversible and tested — upgrade and downgrade both exercised.
8. Every state-changing action the ticket depended on (imports, migrations, fixture/golden capture,
   data transforms) is a script or Makefile/compose target checked into the repo — never a one-off
   command run in a session. Those scripts and all evidence generation execute in Docker. A fresh checkout with the pinned image and required read-only source or
   upstream artifacts preloaded must be able to run the scripts and rebuild the affected artifact
   without network access or an agent.
9. Final review and unresolved findings are recorded against the final diff and gate evidence.
   A named Copilot `judge` is one review mechanism, not an executable merge gate. Failed checks
   prevent completion regardless of a previous verdict. Significant changes require independent review.
10. `CHANGELOG.md` and affected README/docstrings are updated and included in final review.

The PR `Validate repository` workflow runs source-independent fast checks only. Artifact QA,
full coverage, and the fresh Docker E2E requirement remain separate requirements. Browser/API E2E
demonstrates exercised application behavior; it does not establish physical LAN acceptance or
source correctness. Configure the workflow as a required branch check before claiming GitHub
enforces it.

## Coverage floors

Per-package coverage floors (line coverage), not blended across the workspace. Set by ADR-0002.

- **packages/wayfinding**: 85% line coverage

This floor is enforced in the package's `pyproject.toml` via `pytest --cov-fail-under=85` and in
the `make test` gate. Coverage is measured over `packages/wayfinding/src` only (excludes tests).
