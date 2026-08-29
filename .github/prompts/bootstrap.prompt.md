---
description: "Bring the system up from a clean checkout once Phase 1+ containers/services exist (stack up, sample data loaded, gates verified)"
agent: agent
---
Bring the system from zero to running. This command is a no-op until Phase 1 adds `infra/` and a
container-based gate contract — until then, report that status and stop rather than inventing
infrastructure ahead of the code it would run.

Once Phase 1+ infrastructure exists:

1. Run the project's bootstrap target (documented in the then-current `docs/HANDOFF.md`) via
   execute. If any step fails, diagnose and fix — delegate code fixes to `implementer`, data issues
   to `data-qa` — then re-run until green.
2. Confirm no step required installing Python/GDAL/a database driver on the host; if it did, that is
   a harness violation, stop and report it rather than continuing.
3. Invoke `test-runner` for a full gate (test, lint, type, data-QA).
4. Report: services up and their ports, sample data loaded, invariant results, gate summary.
