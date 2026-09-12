# Repository operating instructions

Read `docs/HANDOFF.md` first, then the applicable ticket plan and accepted ADRs.
Current takeover work is tracked in `docs/plans/CODEX-TAKEOVER.md`.
The isolated build increment is `docs/plans/DT-016.md`; the next geometry/source
reconciliation task is `docs/plans/DT-017.md`. Read the current handoff for gate status.
Floor-navigation and route-guidance work is tracked in `docs/plans/DT-018.md` under
ADR-0012. Read the handoff/report for its actual gate and demo status.

## Architecture and boundaries

- Containerized GDAL/Python ETL produces a dual-CRS GeoPackage and contracted
  NetworkX MultiDiGraph. A standard-library HTTP service serves an SVG/JavaScript
  demo and deterministic assistant. FastAPI, MapLibre and LLM orchestration are future work.
- Write only inside this repository. The sibling `dtwin-harness` repository and
  its source FileGDB are strictly read-only. Never repair source data in place.
- All three local geodatabases in `data/` are immutable inputs. Source-etl uses
  local `data/IndoorWayfinding.gdb` read-only; artifact and demo must not access
  raw sources through the repository bind. Keep `/workspace/data` masked in Compose.
- All project code, scripts, tests, builds, data processing, and evidence or hash
  generation run inside Docker containers. The host is limited to repository file
  inspection and editing, Git and Docker CLI operations, and thin Docker launcher
  glue. Do not run host test runners, project code, direct data parsers, or
  evidence/hash processing. This execution policy applies to every agent tier.
  If Docker is unavailable, stop execution; do not fall back to a host runtime.
- Compute geometry and routing deterministically in EPSG:26910. Use vertical_order
  for cross-building floor identity. Preserve parallel graph edges.
- ADR-0005/0009 define measured connectivity: 816 default and 840 elevator-only
  edge-induced components. Fragmentation is expected; reject unsupported routes.
- Room anchors are approximate and same-level. Do not invent connector traversal
  or gap edges. Elevator-only excludes stairs; it is not verified wheelchair access.
- Hashes establish artifact consistency, not independent trust. Only load trusted
  build artifacts; do not replace running-demo artifacts during ETL.

## Delivery and verification

### Model allocation (user preference)

- Use a large reasoning model for planning, orchestration, architecture decisions and
  final judging. Keep task decomposition, acceptance decisions and integration with that lead.
- Delegate bounded, simpler tasks to a smaller worker: mechanical edits, routine
  documentation, running established gates and summarizing their output.
- Choose by task complexity, not role name alone. Escalate ambiguous requirements,
  difficult debugging, security decisions, GIS/routing semantics, or repeated failed
  attempts to the large model. Workers return evidence; they do not approve their own work.
- With the models exposed in this session, use `gpt-6-astra` for the large-model roles
  and `gpt-5.6-luna` for simple workers. These are session routing choices, not claims
  about parameter counts or a persistent runtime configuration.
- For Copilot adapters, keep planning/architecture/judging on the configured Opus
  model without a silent Sonnet fallback; use the configured Sonnet worker for simpler
  tasks. Verify provider availability when invoked; disclose any unavailable tier.

### Parallel delegation (user preference)

- Use multiple concurrent agents by default when independent work is available.
  The large-model lead decomposes the task and delegates proactively.
- Give each worker a bounded objective, explicit file ownership, dependencies,
  validation requirements and an evidence-based return format before starting it.
- Parallelize independent investigations, changes in separate files, documentation
  and read-only reviews. Coordinate shared artifacts, test caches and Compose projects;
  use isolated outputs or worktrees when concurrent work would otherwise collide.
- Keep dependent stages ordered: agree contracts before implementation, demonstrate
  RED before fixing behavior, and integrate completed work before final judging.
- The lead owns integration and conflict resolution. A large-model judge reviews
  the combined final diff and verification evidence. Smaller workers handle simple
  tasks under the allocation policy above; Docker-only execution applies to all agents.

### Workflow

- Preserve inherited dirty files. Do not reset, stash, or rewrite history to simplify a task.
- Keep a ticket plan before behavior changes; demonstrate relevant failing tests,
  implement, run checks, then review the final diff including documentation.
- Use one accountable lead with multiple parallel workers for independent tasks.
  Copilot role files are adapters, not native Codex orchestration.
- Schema/API/component changes require an ADR. Accepted newer ADRs supersede old
  assumptions; update conflicting active instructions in the same change.
- `make gates` runs test, lint, type and artifact data-QA. `make dataqa-source`
  additionally requires the read-only source. `make test-launchers` checks launchers.
- Every green, complete, or ready judgment requires a fresh Docker end-to-end run for each
  delivery, after the final runnable code, configuration, and artifacts are assembled, including
  small and docs-only changes; unit, lint, type, and QA gates alone are insufficient. Exercise
  the changed workflow. Application delivery also requires real demo browser checks and API route
  checks with recorded fixtures and coverage; source or build changes additionally require
  source-to-candidate pipeline verification. Recording that run's evidence afterward does not
  change the runnable state or require a second run.
- The default Compose image must be a real published immutable digest. Local
  investigation may use `COMPOSE_FILES="-f infra/docker-compose.yml -f infra/docker-compose.local.yml"`;
  report that distinction. A local image does not certify publication.
- Record commands, exit codes, skips, image/container identities, artifact hashes, and
  route fixtures/coverage. Any failed or unrun required E2E means incomplete, regardless of
  a previous judge verdict. Browser/API E2E demonstrates exercised application behavior;
  it does not establish physical LAN acceptance or source correctness.
- Update HANDOFF and CHANGELOG with verified state; distinguish historical evidence.
- Keep state-changing data operations in checked-in scripts. Do not push or publish
  unless authorized by the user. Local review and reversible fixes may proceed.
- Use `tools/rebuild.ps1` or `tools/rebuild.sh` for new isolated builds; `make etl`
  requires an unused `RUN_ID` and writes under `build/experiments/`. Completion means
  verified reconstruction, not source-quality approval or artifact promotion.

`docs/DOD.md` defines the quality contract. Copilot-specific workflows remain
available during transition; a nine-role ceremony is not required for each edit.
