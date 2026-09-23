# DT-024 cross-floor room picking

Date: 2026-09-23. Status: implemented and verified in the mounted local demo at
`http://127.0.0.1:18007/`. This is a client interaction change; the API schema,
route graph, exact-topology candidate and artifact hashes are unchanged.

## Failure and correction

The exact immediate workflow was captured in pinned Chromium: click A, switch
floors without waiting, and click B. Known connected fixtures succeeded in AQ and
SH, proving floor identity and submitted endpoint IDs were correct. The remaining
failure was that every room stayed actionable as destination B even when the
directed route-options response classified it as disconnected. A failed or
completed request also made the next room click silently clear A and start a new
pair, and destination submission waited unnecessarily for room-detail metadata.

The client now associates destination availability with the exact A/profile,
highlights connected rooms and disables known unsupported rooms. A click made
while availability is pending waits for that result, so it cannot race into a
known doomed POST. Availability errors remain unknown and preserve the manual
fallback. A replacement room after success/failure changes B while retaining A;
Clear chooses a new A. Route submission and room-detail inspection are independent.

## Test-first evidence

`tests/gate/test_route_options_state.cjs` failed before implementation for all
three corrected state transitions: retained-origin retry, blocked disconnected
room, and destination submission independent of delayed room metadata. A fourth
regression demonstrated the pending-availability click gap before its correction;
a fifth covers a click waiting across a superseding same-origin catalog. All 22
route-options state checks pass after the final client change.

The dedicated real-browser gate is
`tests/browser/crossfloor-room-picking.cjs`. Final evidence is under
`build/navigation-review/crossfloor-room-picking-superseded-final/`.
It uses only visible building, floor and room controls and records route POSTs.
The browser holds two same-origin availability responses and confirms that B waits
for the latest one; the exact click-before-supersession ordering is covered by the
deterministic state test. Completed-route replacement uses real 200 responses. A
single injected 409 response verifies failed-route replacement without depending
on a room that the corrected UI must disable.

| Building | Connected fixture | Result | Known disconnected fixture | Result |
| --- | --- | --- | --- | --- |
| AQ | AQ2035.2 on AQ2000 to AQ5046 on AQ5000 | HTTP/body 200; visits AQ2000, AQ3000, AQ5000 | AQ305 on AQ3000 | disabled; no route POST |
| SH | SH1036 on SH1000 to SH3050.1 on SH3000 | HTTP/body 200; visits SH1000, SH2000, SH3000 | SH005 on SH100 | disabled; no route POST |

Fresh deployed browser suites also passed:

- `navigation.cjs`: all three buildings, all 11 floors, native floor keyboard
  operation, route/floor race and Retry;
- `compact-navigation.cjs`: every recorded floor/room, visible room buttons,
  connected AQ cross-floor route, and 320/390/1440 px layouts;
- `sh-crossfloor.cjs`: clickable and dropdown SH routing, journey floors, and
  Previous/Next across SH1000, SH2000 and SH3000.

The final local Docker gate passed 632 tests, 16 expected skips and 86.43%
coverage. Ruff, Pyright and artifact data QA passed; data QA selected 24 tests,
with 23 passed and one expected skip.

## Boundary

Disabled rooms remain recorded and visible; they are not relabeled as connected.
This change does not invent graph edges. Strand level 100 remains disconnected,
and Strand still has no recorded elevator transition. The broader DT-024 Stage C
draft/explicit-preview workflow and remaining Stage D exploration/cache work are
still open.
