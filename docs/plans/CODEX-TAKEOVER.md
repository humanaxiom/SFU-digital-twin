# Codex takeover assessment and plan

Date: 2026-09-10
Status: Local fixes, clean full gates and Docker-only browser checks passed; published-image access, CI activation and physical LAN acceptance remain open. See docs/reports/CODEX-TAKEOVER.md for current evidence.
Baseline: HEAD `998c477`, plus the existing DT-015 working tree (14 modified files and two untracked files at review start).

## Assessment

The deterministic GIS core is worth preserving. The current product is a containerized GDAL/Python ETL pipeline producing a dual-CRS GeoPackage and a contracted NetworkX MultiDiGraph, with a standard-library HTTP service and an SVG/JavaScript demo. The assistant is deterministic. FastAPI, MapLibre, search-index and LLM orchestration plans are future architecture, not a description of the present runtime.

The strongest decisions are metric computation in EPSG:26910, vertical-order semantics, preservation of parallel graph edges, explicit fragmented-network reachability, conservative elevator-only claims, artifact lineage, and read-only source mounts. The limiting product problem is useful, verified route coverage: approximate room anchors and a fragmented graph constrain what users can actually navigate. More agents or a new map stack do not resolve that data problem.

The harness is a prompt-directed workflow, not an executable orchestrator. It describes nine roles, six prompts, scoped instructions, a post-tool hook, Make gates, and durable ADR/plan/handoff files. Its core loop is planner -> optional architect -> test writer -> RED runner -> implementer -> full gates -> judge -> documentation. Data QA is conditional. The judge is explicitly advisory until CI. At assessment start, the only GitHub workflow published the build image; takeover now adds `validate.yml` for source-independent PR checks, with activation still pending.

## Findings and evidence

These are the initial assessment findings, before takeover fixes. Current disposition
and verification are recorded in `docs/reports/CODEX-TAKEOVER.md` and HANDOFF.

1. **High: the fresh-checkout gate is broken.** `infra/docker-compose.yml:1` still contains `PUBLISHED_DIGEST_REQUIRED`. Existing containers/local images permit investigation but do not establish the promised reproducible baseline. Historical DT-002 tests still require an `etl` service, while the accepted capability split uses `artifact` and `source-etl`.
2. **High: source protection is overstated.** `.github/hooks/enforce-read-only-source.json` uses `PostToolUse`, so it cannot prevent a completed write. Its PowerShell script examines only direct path fields, permits missing/malformed payloads, and does not inspect shell commands. Preserve OS/sandbox restrictions and read-only mounts as the real boundary; test any runtime-specific pre-action hook with harmless fixtures.
3. **High: agent instructions conflict with accepted architecture.** `.github/agents/data-qa.agent.md:12` rejects disconnected default graphs, contrary to ADR-0005/0009. `.github/instructions/spatial-data-invariants.instructions.md:20` requires zero-cost room connectors, while the bounded demo explicitly disclaims connector traversal. These conflicts can cause an agent to reject valid work or invent invalid repairs.
4. **High: LAN request resource limits are incomplete.** `DemoRequestHandler.handle_one_request` acquires a semaphore after a handler thread exists and before blocking socket reads. There is no explicit socket deadline. Slow clients can occupy all slots, with additional threads waiting. Add bounded admission, read deadlines and regression tests before treating this control as satisfied.
5. **Medium: malformed route profiles can raise instead of returning 400.** `server.py:403` tests set membership before checking that profile is a string. A container probe with `profile: []` reproduced `TypeError`. Cover arrays, objects, nulls, booleans and unknown strings at the HTTP boundary.
6. **Medium: UI tests often inspect source text instead of running behavior.** `test_dt015_static_client.py` extracts function bodies with regex and asserts particular identifiers and strings. These tests cannot prove request ordering, stale-response rejection, keyboard behavior, visual layout or mobile behavior. Keep useful static checks, but add executed browser tests for the critical route flows.
7. **Medium: project memory is stale.** Copilot instructions say there is no Makefile; ROADMAP says DT-005 is next; HANDOFF stops at DT-014; DT-015 is labelled Planned despite extensive working changes. Replace status assertions with links to one current state record and evidence tied to a revision.
8. **Medium: build hermeticity is not fully enforced.** Gates do not install packages, but Compose does not disable outbound networking. The base image and Python hashes are pinned; apt package versions are not, so rebuilding the image is not equivalent to using an immutable published image. Separate image-production reproducibility from offline execution guarantees.
9. **Medium: artifact hashes establish consistency, not independent trust.** Routing verifies graph/GPKG hashes against a sibling stats file, then loads pickle. Preserve the trusted-local-artifact assumption explicitly; use an independently approved manifest for promotion. The GeoPackage repository reopens the path after computing its startup hash, so accepted artifacts should be immutable snapshots, not live ETL output paths.
10. **Medium: ETL has no single complete rebuild command.** `make etl` invokes the entry point without a subcommand; that currently prints an infrastructure/no-processing message and returns success. Add an explicit staged rebuild and verification command with separate output directories and promotion, preserving accepted artifacts.

11. **Medium: client state needs behavioral verification.** The profile-change handler only hides the accessibility disclosure; it neither invalidates an in-flight request nor clears/recomputes the displayed route. A displayed default route can therefore remain while the selector says elevator-only. Endpoint activation also awaits room inspection before capturing request generation. Test profile changes and rapid selection/clear sequences with controlled delayed responses.
12. **Low: integration fixtures make feedback unnecessarily slow.** DT-005 repeatedly constructs the real graph in function-scoped fixtures. Use immutable shared fixtures for read-only assertions and small synthetic graphs for local properties, while retaining full artifact checks. Contraction's sampled distance check uses 20 pairs on an undirected default-profile projection; extend confidence with directed and per-profile synthetic property cases rather than treating that sample as exhaustive proof.

## Transition sequence

### Current build — DT-016

Proceed with [DT-016](DT-016.md): executable source comparison and two isolated
legacy rebuilds with source lineage and semantic/room-reachability comparison.
This supersedes treating GHCR/CI/LAN acceptance as a prerequisite for independent
local data/build work. Revised ingestion follows explicit reconciliation of its
141 unassigned additions; no source promotion is implied.

### Local source clarification and mount repair — 2026-09-11

The user confirmed all three buildings' sources are in repository-local `data/`.
Read-only Docker profiling verified ECC, AQ and Strand in both indoor geodatabases.
Directory hashes show local `IndoorWayfinding.gdb` is byte-identical to the previously
mounted sibling copy. Use the local legacy path without changing the accepted snapshot.

The whole-repository bind also exposes local geodatabases through `/workspace/data`:
writable in artifact/source-etl and readable in demo. Restore ADR-0006's capability
boundary by masking that path with an empty read-only mount in all three services;
retain only the explicit read-only legacy source mount in source-etl. First demonstrate
the missing protection with a regression, then verify actual container visibility and
mount flags without attempting any writes to source data. Run focused infrastructure,
launcher and source-QA checks. Existing containers need recreation to receive new mounts;
do not disrupt running demos during this repair.

Revised ingestion remains separate: its pathway layer is renamed and 141 of 22,567
pathways have null facility and level IDs. Reconcile these records before an isolated
rebuild; keep supplemental entrance/door/ramp layers profile-only per ADR-0008.

Completed this scope: four regressions observed RED, then 90 focused tests passed
(2 Docker-CLI skips); Ruff and launcher/no-host-Python gates passed. Actual fresh
containers proved the empty/read-only mask in all three services and explicit
read-only source access only in source-etl. Local source QA passed separately.
The revised ingestion/rebuild steps above remain pending. See
`docs/reports/LOCAL-SOURCE-REVIEW.md` for inventory, hashes and detailed evidence.

### Resumed acceptance work — 2026-09-11

- Run a clean full suite with isolated coverage/output, alongside independent
  published-image access checks and large-model product review.
- Add a repeatable browser gate using the cached immutable Chromium image, on an
  internal Docker network with a fresh read-only demo and no host port publication.
  Exercise actual pointer/keyboard events, the recorded route fixtures, chat parity,
  cross-floor steps, viewport layout and delayed-response regressions. Save screenshots
  and results inside Docker; this does not substitute for a physical second LAN device.
- Reproduce stale scene rendering, incomplete manual-pair state and chat pending-state
  findings before fixing the client. Preserve the existing route/API/GIS contracts.
- Integrate fixes, rerun relevant/full gates, then obtain large-model final review and
  update the handoff. Image access, CI activation and physical LAN acceptance retain
  explicit unverified status until evidence exists.

Docker-only correction (user instruction, 2026-09-11): all project execution,
including diagnostics, data parsers and evidence processing, belongs in Docker.
Host activity is limited to repository inspection/editing, Git/Docker CLI and thin
launcher glue. Move evidence processing and the post-tool diagnostic into the
artifact container, guard legacy PowerShell parsers against host execution, and
verify the replacements with Docker-run tests. No host-runtime fallback is permitted.

Earlier verification (historical): shared instructions and local fixes are implemented.
Full functional suite passed (419 tests, 15 skips); supplemental artifact/synthetic
tests brought combined coverage to 85.38%. Offline fast, artifact-QA and source
count gates passed. Published-image access returns 403 locally; browser automation
reported no browser available through computer-use. The later Docker-only Chromium
gate passed, and independent large-model review resolved further client/logging
findings and the missing Strand fixture. CI activation and physical second-device
acceptance remain open. See `docs/reports/CODEX-TAKEOVER.md` for exact scope and final gates.

### T0 — Capture and reconcile the inherited state

- Preserve the existing DT-015 work; do not reset, stash, rewrite history or fold unrelated edits into a migration commit.
- Record HEAD, dirty paths, active image identity, artifact hashes, gate results and unverified acceptance criteria.
- Reconcile DT-015 against ADR-0010, including browser and second-device LAN checks. Do not mark historical tests as a current approval.
- Exit: one authoritative handoff accurately distinguishes implemented, verified, blocked and deferred work.

### T1 — Establish a reproducible baseline

- Resolve the immutable build-image digest through the checked-in publication workflow; publication/push needs the user's authorization when that step is reached.
- Update obsolete infrastructure tests to the accepted capability split, preserving their read-only and offline invariants.
- Fix the HTTP validation/resource-control findings with failing behavioral tests first.
- Provide one container-only gate entry point; separate fast unit tests, artifact integration, source-required QA, and browser tests. Required source QA must fail clearly if its source is unavailable rather than silently passing via skips.
- Exit: full test/lint/type/artifact-QA baseline passes, with source and browser evidence separately stated and no placeholder digest.

### T2 — Install a portable instruction layer

- Add a concise root `AGENTS.md`: actual architecture, hard boundaries, exact commands, current handoff, acceptance criteria and completion evidence.
- Keep accepted decisions in ADRs and shared engineering documents. Make the Copilot entry file a thin adapter to those documents during transition.
- Port reusable workflows to repository skills only when needed; do not mechanically translate all nine role files or their Copilot-specific model/tool names.
- Resolve old connectivity, connector and status statements explicitly. Runtime permissions and container mounts enforce boundaries; markdown explains them.
- Exit: a fresh Codex session identifies current work, runs the right checks, respects the source boundary and reports incomplete work accurately.

### T3 — Make completion evidence executable

- Add pull-request validation CI using the immutable image. Keep private source datasets out of public CI; use approved fixtures and a separate authorized source-QA runner.
- Bind evidence to commit plus dirty-diff identity, image digest, artifact manifest, commands, exit codes, skipped checks and unresolved findings.
- Use one accountable lead agent, with bounded independent review for significant changes and GIS review for graph/data changes. Do not require a full sequential role ceremony for every small edit.
- Review the final diff after documentation changes; retain TDD for behavior changes and justify any test-contract supersession by ADR.
- Exit: a failed required check prevents completion independently of an agent's prose verdict.

### T4 — Prove the takeover on a bounded ticket

- Deliver one small end-to-end defect fix through plan, RED, implementation, gates, review and handoff.
- Evaluate correctness, relevant test coverage, reproducibility, user interruptions, review findings and stale-instruction incidents.
- Retain the Copilot adapter until the pilot passes; avoid simultaneous competing edits to the same files.
- Exit: another fresh session can continue from the recorded evidence without reconstructing chat history.

### T5 — Resume product work by evidence

- Finish DT-015 acceptance and restore reliable gates before expanding the architecture.
- Profile revised source independently; compare unit-pair reachability and anchor quality against the accepted baseline before promotion.
- Prioritize room-entry correctness, route coverage, disconnected-route explanations and real browser usability. Add FastAPI/MapLibre/search/LLM components only for a demonstrated requirement.

## Inherited assessment evidence (not rerun by reading this file)

- Read-only repository, history, working-tree, architecture, harness and selected implementation/test inspection.
- Existing `sfudt-wayfinding-dt015-18090-artifact-1` container used; no host Python/GDAL and no source import or image publication.
- Ruff: passed. Pyright: zero errors/warnings.
- Artifact data-QA: 22 passed, one skipped, one failed (missing image digest), 400 deselected.
- Malformed-profile probe reproduced the TypeError described above.
- Full suite: 401 passed, 8 failed, 15 skipped in 505.71 seconds. Coverage 82.01%, below the 85% gate. Failures: two missing-digest assertions; four obsolete DT-002 etl-service assertions; two DT-003 error-path tests that require source existence in the artifact-only container. This contradicts the handoff claim that the digest is the only remaining full-gate blocker. The existing local container reported Python 3.14.4; this is a local-image baseline, not a published-image certification. No browser or second-device LAN validation was performed in this review.

## Codex documentation basis

The proposed instruction entry point and reusable workflow packaging follow official documentation: [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [skills](https://learn.chatgpt.com/docs/build-skills). Copilot-specific role files and hooks require deliberate adaptation; this plan does not assume native execution compatibility.


