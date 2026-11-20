# DT-024 journey, exploration and scene reuse

The Stage D baseline is the Stage C checkpoint at `827263c`. The
[navigation plan](../plans/DT-024.md) and [ADR-0017](../adr/0017-navigation-state-and-journey.md)
define how instruction selection, floor exploration and scene loading interact.
All verification uses Docker. The source datasets and routing artifacts are
unchanged by this client increment.

## Baseline and regression coverage

On the real AQ2035.2 → AQ5046 elevator-only route, selecting a visit, advancing
and reversing a step, and switching transition phases already selected the
expected geometry. Browsing a different floor still showed Previous and Next,
and the context read “Floor.” At 390×844 the Arrival action extended below the
viewport and Next started at y=877. Chromium `c129eaa6eb5f` exited 1 on the
focused journey probe (`dt024-stage-d-journey-red`).

The Docker client test for artifact-scoped scene reuse also failed at baseline
(`1364139cfe60`, exit 1). It exercises duplicate loads of the same floor,
overlapping loads across two artifact identities, a mismatched response and
retry, adjacent-visit prefetch, and eviction after eight other exact floors.
The implemented cache retains eight scenes and only shares pending requests
within the same artifact. A background completion fills the cache without
changing the displayed floor or its status.

## Journey and recovery fixtures

- **Instruction order and transition controls (N07–N09).** AQ2035.2 → AQ5046
  with Elevator only travels directly from AQ3000 to AQ5000. The probe checks
  both authored phases and the absence of an AQ4000 visit or route span.
  AQE2-1 → AQ3019 revisits AQ4000 and AQ3000. The browser selects both AQ3000
  occurrences by visit ID and advances and reverses from the second. Exploration
  preserves the selected occurrence while users inspect another room or campus.
- **Guidance and endpoint outcomes (N10–N11).** SH1001C → SH1003 supplies real
  available guidance and AQ1003 → AQ5053.2 supplies real limited guidance.
  The accepted catalog supplies disconnected destinations. Controlled responses
  cover unavailable guidance, a same-anchor destination, an unmapped endpoint and
  an unavailable connection check. An explicit Preview after an unknown check
  still exercises the real route service.
- **Scene recovery and camera (N12).** A delayed 503 leaves the previous floor
  labeled and visible. Keyboard Retry opens the requested floor. The client
  regression also checks that Retry on a failed instruction resumes that exact
  route step and that returning to the route restores its deliberate zoom.
- **Scene identity and timing (N14).** A response whose layer provenance differs
  from the loaded artifact is rejected before caching. A pending request for a
  previous artifact cannot replace a newer floor. Browser probes on the accepted
  artifacts and the Strand candidate fetched SH1000 (65 rooms) and SH3000 (136
  rooms), then revisited SH1000 with identical SVG geometry and zero further
  transfers or parses. These timings are single observations in local Docker.

| Artifact | Floor | Transfer (ms) | Parse (ms) | SVG render (ms) |
| --- | --- | ---: | ---: | ---: |
| Accepted | SH1000 | 1433.6 | 2.4 | 21.5 |
| Accepted | SH3000 | 1256.9 | 3.3 | 36.2 |
| Accepted | SH1000 revisit | — | — | 14.6 |
| Strand candidate | SH1000 | 1396.1 | 2.1 | 18.5 |
| Strand candidate | SH3000 | 2200.1 | 6.1 | 38.1 |
| Strand candidate | SH1000 revisit | — | — | 23.9 |

## Reproducing the browser runs

Use the Compose and read-only mount commands in the
[Stage C report](DT-024-PREVIEW.md). Use a fresh private demo when starting
an independent suite so that a previous Chromium process reusing the same
container IP does not consume its request allowance. Two consecutive-suite
room-picking runs hit HTTP 429. The same probe against a fresh demo passed.
The Strand step probe was updated to open **All directions** before clicking
an instruction. Both changes exercise the production limits and controls.

The retained Strand candidate is `sh-navigation-exact-20260923`; the rebuilt
candidate is `dt017-history-20261120-v1`. The accepted and Strand artifact
hashes are in the [Stage C report](DT-024-PREVIEW.md) and the result JSON.
All demo runs used local image `d7b70c51d54d` and pinned Chromium 130.
Docker measured the final client files as follows.

| File | SHA-256 |
| --- | --- |
| app.js | `b14a0f810ff1175a3d831923d16bc6d724f7e5a1e24de6b5008ddab1c40103f4` |
| index.html | `c56bd23495967a57c7d5e559b296f6e1902074d51030a38b0797bec14ba13518` |
| styles.css | `c6c4193214a2ff8f13401a4ee8174b33d4fc6ea8f9562d223c6295444c0e1127` |

Each row below ran `node tests/browser/<probe>.cjs` in the pinned browser and
exited 0. The result and screenshots are under `build/navigation-review/<label>/`.

| Probe | Acceptance coverage | Label | Result SHA-256 |
| --- | --- | --- | --- |
| navigation | N01–N04, N12; all buildings, out-of-order navigation and scene Retry | stage-d-navigation-final-candidate | `d7ce33e3fb5b504dccd789458f1116571e55156bff0755e3ab421af2d3acd84a` |
| room-search | N05, 15 checks | stage-d-delivery-room-search | `0d6ffcbdaaa940ba349b2829b2db37536d7960782ba300d135248e112701f08a` |
| preview-route | N03–N06, 11 checks including real Strand route, reverse and elevator-only 409 | stage-d-delivery-preview-route | `1af8e5668d6f7e2e9f43b205bdedb98b0081c4d21ced6304b6fa4540e015398a` |
| stage-d-recovery | N10–N12, six checks, 10 route POSTs across desktop and mobile | stage-d-recovery-delivery | `20157f0b0d0cc43485ce3c4152cba980f3c0d336fe361fb448156f05f5fdf944` |
| sh-crossfloor | N07, five Strand floor/step checks | stage-d-strand-final-sh-crossfloor | `0ef603e891c07990c967874dca0282a976c4750d0e2d171aac17b4602a24b4af` |
| compact-navigation | N01, N13; six checks with 3 buildings, 11 floors and 320/390/1440 px layouts | stage-d-strand-final-compact-navigation | `b5b3df2185c6190bd222628626a4dca460a0bea622a25fa9814482026da9c203` |
| scene-cache | N14, Strand candidate | stage-d-cache-final-candidate | `46bc05318222ba2b35e5715652104a78204d181ef6312b1837716d2bb2c9a58c` |
| scene-cache | N14, accepted artifacts | stage-d-cache-final-accepted | `f0247ee3cf8352a1372e62d2378098b0f29f91af0d696e8515407f3fa2c698f4` |
| crossfloor-room-picking | N15–N16 as revised by Stage C; inspect, choose endpoints and Preview | stage-d-isolated-crossfloor-room-picking | `a59b55c0584d14f0cca91883e51ae1cf63785e5d525ab588e68c4e0237743fb1` |

For the N07–N09 and N13 journey probe, set
`WAYFINDING_BROWSER_JOURNEY_ONLY=1` on the Compose browser service and run
`node tests/browser/demo.cjs` against the accepted artifacts. The final
`dt024-stage-d-journey-green-final` run (demo `c9e0f59d0802`, Chromium
`c7ad1bfd290f`) passed the two real AQ routes with keyboard, touch, camera
restoration, reduced motion, and sticky controls during scrolling at 390 and
320 px. Chromium and teardown both exited 0. Screenshots and result SHA-256
`b394a98418a3c79a1ea5a68981cf324756d189884f54f4dcfc8ccbfe0f006eb3` are under
`build/takeover-browser/dt024-stage-d-journey-green-final/`.

## Integrated Stage E gates

The client revision is `628c3c2`. The artifact service in Compose project
`sfudt-staged-pkg` used `infra/docker-compose.yml` and
`infra/docker-compose.local.yml`. With `PYTHONPATH=/workspace/packages/wayfinding/src`,
Ruff, Pyright, the stack and rebuild launcher checks, and the host-execution
policy check all exited 0. Artifact QA (`pytest packages/wayfinding/tests -m
dataqa --strict-markers --no-cov`) passed 23, skipped one and deselected 656.
The full `pytest packages/wayfinding/tests -q -rs` run in container
`8879f73ede3a` exited 0 in 462.14 seconds with **664 passed, 16 skipped and
86.96% coverage**. The skip list in `build/dt024-staged-delivery.log` covers
source-only tests, unavailable Docker CLI and Make inside the image, and a
profile-specific same-anchor fixture absent from the accepted artifact.

The final comprehensive `node tests/browser/demo.cjs` runs opened visible
disclosure controls and exercised actual routes, assistant parity, exact
geometry, delayed requests, reduced motion and HTTP 409. An earlier canonical
run hit the server’s request limit after scene reuse shortened the run. The
browser now waits for its observed POST window when needed; the canonical
delivery waited 18.569 seconds. Both runs covered desktop and mobile.

| Artifacts | Fixtures per viewport | GET / POST | Result under `build/takeover-browser/` | Result SHA-256 |
| --- | ---: | ---: | --- | --- |
| Accepted | 4 | 85 / 33 | dt024-stage-d-canonical-final-c/results.json | `e3bc560f87c136bbcc5485270d309d96a97df91d9b183b8b48ccf67eeb27a3e5` |
| Rebuilt candidate | 8 | 58 / 26 | dt024-stage-d-candidate-final-b/results.json | `ad3dcc001ff133a7dcd58e7379abc8ba26004aede1a52b5e6bad286660a4371f` |

Both comprehensive browser processes and their teardown commands exited 0.
Accepted demo/browser IDs were `671cc5ef7f81` and `3fe99501f42b`. Rebuilt
demo/browser IDs were `7a0729d9a2fa` and `831444a8b6a3`. The existing demo
and edge proxy remained healthy. The current indoor sources cover AQ, ECC and
Strand Hall. The rollout now moves to review of a further Burnaby building.

Independent `gpt-6-astra` review approved DT-024 Stages D and E for the local
pilot. The reviewer checked the combined diff, recalculated all 12 browser result
hashes and the client hashes in Docker, confirmed the full-suite result and
inspected the 320 px screenshot. The next data admission has its own review.
