# 29. Identify the loaded navigation script and notify retained tabs

Status: accepted and locally verified; [DT-038 evidence](../reports/DT-038.md).
Date: 2026-11-20

## Contract

The additive GET /demo/v1/client endpoint (no query) returns exactly protocol: 1
and script_sha256: a lowercase 64-character SHA-256 of the current raw app.js
file. It is read dynamically on each request, not cached at Python startup.
Existing health/data/static URLs and admission/security policies remain intact.
The endpoint measures served source consistency, not release trust or chronology.

For app.js responses only, read raw bytes once, hash those same bytes, and append
newline/semicolon followed by setLoadedClientRevision with that safe literal.
Keep the strict directive and original program intact. The digest describes
raw executable source excluding this generated identity hook. The checker starts
only when the hook supplies its loaded identity, never by treating a later
endpoint fetch as the loaded baseline. If unavailable it stays unverified.

Expose Check for updates in data details, plus an accessible status and a visible
notice when a different script identity is observed. Check initially and on a
visible-return event, with automatic requests at most once per minute and one
in-flight request. Manual checks join an active check. Bound fetch AND body
completion to five seconds and abort on timeout. Malformed, missing, failed or
timed-out checks are unknown, never current. Observing a mismatch is sticky:
subsequent failures or server rollback cannot erase that observed-change notice.
Say a different version was observed, not that hash order proves a newer release.

Never reload, navigate, reset state, mutate route drafts/committed routes, change
floor/camera/inspection or send route requests during update checks. Offer an
explicit Open updated app link to /index.html in a new tab, noopener, explaining
that the new tab starts fresh and the existing tab keeps its route.

Scope is app.js code identity only: HTML/CSS-only changes are not detected.
Tabs running pre-checker code require one fresh load before this safeguard works.
No polling timer, data processing, persistence/migration or source promotion.

## Acceptance

Real browser RED then GREEN: loaded A/current B with identical data preserves
retained document/navigation snapshots and makes no route POST; A/A is current;
request/body hangs terminate, invalid/offline results stay unknown; a late result
cannot erase observed mismatch or replace a completed newer check. New-tab link
keeps original state. Desktop and 320/390px layouts expose the notice and controls.
HTTP tests prove raw/served stamp correspondence, bind-source change detection,
unchanged health and static behavior, and query/method rejection. Run all existing
navigation, Preview, scene recovery and canonical API E2Es plus required gates.
