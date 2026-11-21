# Documentation and GitHub checkpoint — 2026-11-20

Application baseline: `16dcde50bfd20b76fe46df824438fd1226715379`.
Branch: `feature/burnaby-building-intake`. Working tree was clean at intake.
The user authorized updated docs, plan and handoff, followed by commit and push.

## Scope and preservation

Updated HANDOFF, CODEX-TAKEOVER, ROADMAP, DT-038's subsequent authorization note
and CHANGELOG, with a separate checkpoint plan. Historical delivery evidence is
retained. Default two-room routing, explicit Preview, inspection, exploration and
return, floor Retry, complete geometry and retained-tab safeguards remain intact.
No removals were requested or implemented. Runtime, tests, deployment configuration,
source data and artifacts are unchanged.

ASB remains footprint-only pending keyed facility/level/room records. DT-017's
141 revised pathways still need reviewed assignments. JavaScript-only update
checking requires one fresh load for pre-checker tabs; the original stalled-tab
transport cause remains unconfirmed. Published-image execution, required CI
checks and physical LAN acceptance remain open.

## Fresh verification

Runs below execute in Docker after the unchanged final runnable state. Dates in
raw evidence use UTC (2026-11-21); the delivery date is 2026-11-20 in the user's
America/Whitehorse timezone. Established suites and assertions are unchanged.

The short live rehearsal used the pinned Playwright image
`mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`,
Chromium 130.0.6723.31, container
`4734106aefe71c40f75408d8f8c0707305b766ad8c25a011d00f850824db5291`.
`WAYFINDING_BROWSER_CLIENT_ORDINARY_ONLY=1 node tests/browser/client-update.cjs`
against `http://demo:18107` exited 0. Initial and manual identity checks retained
the real SH1036 → SH3050.1 default route (one route POST), SH2145 inspection on
SH2000, document, endpoints, instruction and camera. No fault injection.
Evidence: `build/navigation-review/docs-checkpoint-live-20261120/results.json`,
SHA-256 `eaaffb9e72dd85d91b2725243806d24499e4396f6c5070a7eeb4c4f292e67a68`,
computed inside Docker. The browser used read-only root `tests/browser`, writable
`build`, `--add-host demo:host-gateway`, and the matching run label. No live
service was restarted or reconfigured.

Full package, lint/type/artifact QA and source-to-candidate pipeline were not
rerun for this documentation-only change. DT-038's 704 passed / 16 skips /
87.54% coverage belongs to its prior delivery, not this checkpoint. Fresh browser
checks do not certify registry publication, source correctness or physical LAN.

## Isolated browser/API preservation runs

Both Compose startup/health checks and both browser commands exited 0. Each
suite had a separate internal network and service, with no host port publication.
Only package source, tests and the fixture report were mounted read-only; build
output was writable. No raw source data was exposed. Configuration is retained at
`build/docs-checkpoint-20261120-browser.yml`.

| Suite | Demo container | Browser container | Result SHA-256 |
| --- | --- | --- | --- |
| Candidate `node tests/browser/two-room-click.cjs` | `5cc75d4f3c95` | `4a176f96d2fa` | `fba5a3dcece29bb47bd103bbbc81a6b588ca3e6717f620ea4a5680ffb0fc677a` |
| Accepted `node tests/browser/demo.cjs` | `b84ab07bb692` | `c0c1d4f194b2` | `0f96305118d2a96cb7c630984092decd4392747a8a99575786f3668148d5a7bf` |

Candidate results are at
`build/navigation-review/docs-checkpoint-candidate-two-room-20261120/results.json`.
They exercise normal default pointer/keyboard room selection, direct API edge
and distance parity, replacement B, inspection, delayed availability, Clear and
unsupported-destination preservation at desktop/mobile/320px widths.
Canonical results are at
`build/takeover-browser/docs-checkpoint-canonical-20261120/results.json`.
All four recorded fixtures passed at 1440×1000 and 390×844 (AQ elevator, long
corridor, stairs and Strand corridor), alongside guidance, chat parity,
pointer/keyboard, campus and journey cases, negative HTTP409, delayed responses,
320px layout and reduced motion. The run recorded 87 reads and 33 POSTs. No
suite or baseline assertion was skipped or relaxed.

Both demos used local `wayfinding-build:local`, image ID
`sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`;
both browsers used the immutable Playwright image recorded above. This is local
image verification, not published-image certification.

Artifact identities, computed inside Docker:

| Set | File | SHA-256 |
| --- | --- | --- |
| Accepted `build/` | `wayfinding.gpkg` | `f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65` |
| Accepted | `graph_contracted.pkl` | `ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d` |
| Accepted | `graph_contracted_stats.json` | `2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1` |
| Candidate `build/experiments/sh-navigation-exact-20260923/derived/` | `wayfinding.gpkg` | `da44fc5683169c53efcc0b2080cea4419ff40833dad8fb47c8b76051ec656eac` |
| Candidate | `graph_contracted.pkl` | `93c2ff2994e6e564adecae3506175f2c0047948e1d84e44045d2c70267071d46` |
| Candidate | `graph_contracted_stats.json` | `9a678cb044f6c76d3abf61bfa57a0e56fafb00efb0d181f5a7906492b23a6cfb` |

Reproduction uses `docker compose -p <project> -f
build/docs-checkpoint-20261120-browser.yml up -d --wait demo`, then
`docker compose -p <project> -f build/docs-checkpoint-20261120-browser.yml run
--name <browser> --no-deps browser node tests/browser/<suite>.cjs`.
Candidate project: `docs-checkpoint-candidate-20261120`,
`DOCS_CHECKPOINT_ARTIFACT_DIR=C:/repos/sfudt/ghcp/build/experiments/sh-navigation-exact-20260923/derived`,
`DOCS_CHECKPOINT_LABEL=docs-checkpoint-candidate-two-room-20261120`.
Canonical project: `docs-checkpoint-canonical-20261120`, artifact directory
`C:/repos/sfudt/ghcp/build`, label `docs-checkpoint-canonical-20261120`.
Startup/browser logs are retained under `build/docs-checkpoint-20261120-*.log`.

Docker validation found zero missing local Markdown link targets across the
seven edited/new documents (exit 0); `git diff --check` also exited 0.
Independent `gpt-6-astra` documentation review found no substantive blockers;
its requested evidence report and terminal-newline correction are included.
The documentation commit is followed by the user-authorized branch push; the
actual commit and remote result are reported in the delivery response.

The candidate run recorded three direct API fixtures and six invariant checks;
the canonical run recorded seven additional checks beyond its viewport fixtures.
Both owned temporary Compose projects were torn down with exit 0. The completed
live browser container was removed after identity capture; evidence is retained.

Final independent `gpt-6-astra` review approved the assembled documentation and
verification record for the authorized commit and branch push, with no blockers.
Owned teardown commands were `docker compose -p <project> -f
build/docs-checkpoint-20261120-browser.yml down --remove-orphans` for the two
projects named above; both exited 0. Existing live services were untouched.
