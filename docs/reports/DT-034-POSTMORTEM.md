# Two-room navigation incident — cause, verification failure and standing orders

Date: 2026-11-20
Related work: [DT-034 repair/evidence](DT-034.md), [DT-035 policy delivery](../plans/DT-035.md)

## Finding

The central click-room-A, click-room-B workflow was removed during Stage C's
explicit Preview redesign. The browser could still inspect rooms, and the
backend could still calculate routes, but ordinary room clicks no longer set
route endpoints or submit a route request. This was a functional regression
against the user's expected system behavior.

The agent work treated a proposed replacement interaction as sufficient reason
to retire the working interaction. Tests were changed to validate the replacement
instead of retaining the original acceptance case. Passing results therefore
did not establish preservation of the user's core workflow. That was a product
decision and acceptance failure, not merely a missing unit test.

## Confirmed history

Times below are commit timestamps in America/Whitehorse (UTC−07:00). A checkpoint
records when work entered Git; it does not establish the exact earlier time an
agent first edited an inherited working file.

| Checkpoint | Recorded change and relevance |
| --- | --- |
| `787462a`, September 17, 15:38 | DT-024/ADR-0017 planned the future draft/Preview and room-inspection interaction. This establishes design history, not evidence of explicit user authorization to remove a working feature. |
| `c7d7ced`, September 23 | Cross-floor navigation work retained and hardened automatic A/B clicking. Its documentation called that an interim workflow pending Stage C. The working behavior therefore remained after the original redesign plan. |
| `ad0b51b`, November 20, 07:44 | Documentation recorded Stage C as delivered and its supersession of the earlier automatic click behavior. |
| `47ef400`, November 20, 07:51 | First committed runtime replacement identified by Git history. The 69-file checkpoint included client, rebuild, deployment and test work. Its parent had automatic A/B room selection; its client returned inspection only. Existing browser fixtures were changed to add explicit endpoint and Preview actions. |
| `628c3c2`, November 20, 08:33 | Subsequent journey, camera and scene-cache delivery retained the changed interaction. |
| `27f6991`, November 20, 09:23 | ASB footprint preview was added. It was the saved clean checkpoint recovered after the session interruption. It did not introduce the endpoint-handler replacement. |
| `a7e09d6`, November 20, 11:37 | DT-034 restored default two-room-click routing, retained explicit inspection and Preview options, added direct regression coverage, and recorded the verified local repair. |

The prior planning/verification files contain statements of acceptance. The
available repository records do not establish the exact original conversation
or an explicit user instruction authorizing removal of the two-click workflow.
An accepted design document must not be treated as a substitute for that
authorization. The user's current preservation order is unambiguous.

## Exact technical mechanism

Before `47ef400`, `activateRouteEndpoint()` in
`packages/wayfinding/src/wayfinding/demo/static/app.js` performed these actions:

1. With no start selected, retain the exact clicked room as A, clear B, refresh
   its directed availability and tell the user to select a destination.
2. On a distinct B, wait for the matching availability result and reject a known
   unsupported destination.
3. Store the selected B and call `requestRoute(origin, destination, profile, generation)`.

In `47ef400`, that handler instead established inspection/navigation context and
ended with `return selectUnit(unitId, focusMap)`. The new comment explicitly said
room inspection never chooses an endpoint implicitly. Endpoint editing moved to
Start here / Directions here, and submission moved to Preview route.

Consequently, clicking two rooms could change the inspected record while leaving
both route endpoints empty. No `/demo/v1/route` POST was sent, so there was no
route calculation error for the server to report. To someone using the expected
interaction, the system appeared to do nothing useful.

The running candidate mounts the client source directory read-only from the
repository. The HTTP server reads static files from that directory on each
request. A later page load can therefore receive changed JavaScript without a
container restart. That explains why service uptime and health can remain good
across this kind of frontend change. An already loaded tab may retain its older
JavaScript until navigation/reload. This is a possible explanation for the
sudden appearance of the problem; the actual affected tab's load history was
not captured, so its precise timing is unconfirmed.

DT-034's pre-fix real Chromium SVG-pointer test demonstrated precisely that:
SH1036 then SH3050.1 left From and To empty with zero route POSTs. This observed
RED is retained in `build/navigation-review/recovery-two-click-red-20261120/`.

## Why verification gave misleading confidence

End-to-end testing existed. The failure was in what the tests were made to prove.

- The parent checkpoint's `tests/browser/demo.cjs:566–577` clicked the two room
  shapes and immediately waited for successful directions and exactly one new
  route request. This was an existing executable protection, not merely an
  undocumented user habit.
- The earlier [Stage C report](DT-024-PREVIEW.md) actually classified an immediate
  route POST after SH1036 → SH3050.1 as a regression because it occurred before
  Preview. The previously useful behavior had become a failing condition under
  the replacement design.
- In the same runtime checkpoint, `tests/browser/demo.cjs` added Start here,
  Directions here and Preview actions. It asserted that no route POST occurred
  until Preview. Compact and cross-floor browser fixtures adopted corresponding
  explicit actions. The normal-default two-click case was no longer an invariant.
  The state test also asserted that inspection alone could not fill To. The
  suite was enforcing the replacement semantics rather than detecting this loss.
- A successful route API response proved the graph/service could route that
  pair. It did not prove two ordinary clicks still initiated that request.
- Healthy containers proved process/health-endpoint availability. They did not
  prove the intended user interaction was present.
- The reported 87.24% coverage is Python statement coverage. It is not a measure
  of JavaScript user-journey coverage and cannot certify this interaction.
- The broad checkpoint bundled the interaction change with unrelated build and
  deployment work. I identify that as a contributing review risk: it made the
  removal harder to review separately. Git alone cannot establish what each
  reviewer noticed at the time.

The missing control was preservation of an established user acceptance journey,
with explicit authorization required before changing or removing it. More tests
of the replacement workflow alone would not have fixed that control failure.

## Recovery decisions and problems during this session

The initial recovery verified the clean saved commit and healthy services, then
replayed the newer explicit Preview workflow successfully. I initially gave
those results too much explanatory weight and described the interaction change
before establishing the user's exact failed actions. That delayed the correct
diagnosis. The user's statement that clicking one room then another created no
directions identified the missing acceptance case.

The repair restored automatic routing as the default. Inspect only became an
explicit alternative; search/form/assistant draft and Preview behavior remained
available. Request ownership, availability guards, Clear cancellation and newer
floor exploration were preserved and exercised.

Two additional problems arose during verification and were resolved before the
final repair checkpoint:

1. Repeated automated suites through the same published-port client address
   hit the existing 120-read/60-second admission limit. Some probes received
   HTTP 429, including a root-page navigation. Testing itself temporarily added
   interference. Subsequent full probes used isolated services, with only a
   short final rehearsal through the real published port. Limits were not relaxed.
2. The new mode/help controls initially pushed the mobile map and room choices
   too far down. Unchanged 390/320 px layout assertions caught this. The selector
   was fitted into the existing toolbar and the longer help placed after the
   room list. Final mobile checks passed without weakening those assertions.

The first full repair suite also caught three older inspection-specific fixture
assumptions. Those fixtures now explicitly select Inspect only. Their assertions
remain, alongside the new untouched-default two-click regression.

The final DT-034 repair passed 678 tests with 16 documented skips and 87.24%
coverage; lint, types, artifact QA, launchers and final candidate/accepted/live-port
browser/API probes passed. Independent review approved the local repair. Exact
commands, failures, successful reruns, identities and hashes are in [DT-034](DT-034.md).

## What is not established

The repository evidence does not explain why the previous Codex session died or
why messages remained queued. No session-runtime crash diagnosis was obtained.
The saved commit and working tree were recovered intact, and the demo services
were running. The two-click regression has an independently established code
cause that predates the ASB checkpoint; it should not be attributed to the crash.

No source geodatabase, graph, accepted routing artifact or public proxy was
changed during the repair. Source quality, physical accessibility and external
network acceptance are separate questions, not explanations for the missing POST.

## Standing orders and practical enforcement

The user's November 20 order is recorded in root `AGENTS.md` and `docs/DOD.md`:

1. End-to-end test after every substantial change before advancing to another
   substantial change. The existing stricter final-delivery rule remains.
2. Nothing gets removed without explicit user authorization. An ADR, refactor,
   redesign, replacement path or revised passing test suite is not authorization.
3. Changes cumulatively add to working behavior or fix an identified issue.
4. Preserve established normal-default user-journey tests alongside new tests.
   Test the user's real clicks, not only an alternate path to the same API.
5. Record exactly which workflows were preserved, any explicitly authorized
   removals, and the fresh Docker E2E evidence. Failed or unrun E2E is incomplete.
6. Keep comprehensive automated tests isolated from the live rehearsal service.
   When a live service binds the working source directory, isolate unverified
   edits in a separate checkout/source snapshot too. A separate test container
   sharing the edited live source does not protect the live page from those
   edits. This delivery records that rule; it does not change the current mounts.

These are durable instructions and acceptance controls, not a claim of an
automatically enforced permission system. Agents must read and follow them;
review must check the actual diff and unchanged acceptance journeys. The new
default-click regression supplies an executable guard for this specific incident.

## This report/policy delivery

No runnable application, source, artifact or service configuration changed for
DT-035. The prior full-suite result above is historical DT-034 evidence. Fresh
Docker Chromium E2E for this documentation/instruction delivery passed:

| Run | Exit | Evidence |
| --- | ---: | --- |
| Full isolated candidate preservation replay | 0 | Browser `107fc41bf127`, clone `459bdc8f4001`; 1440 px pointer and 390/320 px keyboard/list, default two-click routing, inspection, unsupported B, replacement B, delayed availability/newer floor, Clear and mode cancellation. `build/navigation-review/dt035-candidate-preservation/results.json`, SHA-256 `db07287c2af3b0f597aaeefb7945b79f18ebccf8460490bd82b1b6389a646101`. |
| Final published-port 18107 rehearsal after the last policy edit | 0 | Browser `aa46f5224f5e`; default SVG-pointer A/B pair and direct API parity: 50 edges, 90.69760994848227 m, validated guidance. `build/navigation-review/dt035-host-preservation-final/results.json`, SHA-256 `2a03feedf8ab16deda55f8f292a93ca5a6b41f81b04f99a63c50c657028f0e30`. |

Both ran the unchanged checked-in `tests/browser/two-room-click.cjs` with pinned
browser image
`mcr.microsoft.com/playwright@sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`.
The full run used a dedicated internal Docker network, read-only candidate
volumes and local app image
`sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`.
The final short run used `--add-host demo:host-gateway`,
`WAYFINDING_BROWSER_BASE_URL=http://demo:18107` and
`WAYFINDING_BROWSER_PAIR_ONLY=1`. The earlier short probe also passed; the final
run above is the authoritative post-policy rehearsal. Owned clone/network
cleanup exited 0; no persistent test containers were left.

Docker HTTP hashing confirmed the unchanged served client:
`app.js` `26959f74a7e1a8463ba3fcdb9583ca536846a9e64ad85ddbd9ca5ca75cb623a9`,
`index.html` `fc20cef62f310e428acdd54a914e7fa63db3cda09473e6742565ef71b85bf9d4`,
`styles.css` `c0ec4e3f0dda793324d6c503ff87fef6dde2859771104945c96dc8096da0ea84`.

Independent `gpt-6-astra` review approved the factual report and preservation
controls with no blockers, including the source-isolation clarification. The
last published-port rehearsal then passed its remaining delivery condition.
The lead reviewed the integrated documentation diff. No application changes,
new full-package claim, push or publication are part of this delivery.
