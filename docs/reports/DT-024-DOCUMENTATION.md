# DT-024 documentation delivery

Scope: navigation review, implementation plan, accepted client architecture and
project documentation. No runtime code, API, GIS artifact or deployment change.
The DT-024 implementation ticket remains open; its RED and acceptance matrix have
not yet been implemented. This report covers only the planning/architecture PR.

## Change

- DT-024 defines staged delivery and N01–N14 user-task acceptance.
- ADR-0017 accepts the state/draft/journey contract for implementation and narrowly
  supersedes client interaction choices in ADR-0012/0013/0016.
- System design distinguishes the current HTTP/SVG demo from future product
  architecture; roadmap, README and indexes point to the next client increment.
- Navigation review records reproduced failures and separates UI behavior from
  graph/geometry constraints. Existing local deployment notes are preserved.

## Validation commands and identities

All runtime checks execute in Docker. Existing local toolchain image:
`sha256:d7b70c51d54d661d2932aa7c5a2263d4af7f2168c17711bd05a67f4f5ad0851a`.
Published image registry access was unavailable locally; these checks do not certify
published-image deployment. Deployed demo:
`sfudt-wayfinding-18000-demo-1`, loopback http://127.0.0.1:18007/.

Package commands execute in `sfudt-wayfinding-18000-artifact-1` with
`PYTHONPATH=/workspace/packages/wayfinding/src`:

```
pytest packages/wayfinding/tests
ruff check packages/wayfinding
pyright packages/wayfinding/src
pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov
```

Boundary checks: `sh tests/gate/test_launch_stack.sh`,
`sh tests/gate/test_no_host_python.sh`, `sh tests/gate/test_rebuild_launcher.sh`.
Local logs: `build/navigation-review/dt024-*`.

Fresh existing browser/API E2E uses the pinned Playwright image
`sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`,
`--network container:sfudt-wayfinding-18000-demo-1`, and repository read-only
package/browser/fixture mounts plus writable build evidence. Command:
`node /workspace/tests/browser/demo.cjs`; environment:
`WAYFINDING_BROWSER_BASE_URL=http://127.0.0.1:8080` and
`WAYFINDING_BROWSER_RUN_LABEL=dt024-documentation-20260917`.
Evidence: `build/takeover-browser/dt024-documentation-20260917/results.json`
and screenshots. This exercises the existing application, not unimplemented DT-024.

## Results and independent review

Fresh browser/API E2E passed (exit 0), completed 2026-09-17T22:32:02.321Z:
all four canonical fixtures at desktop 1440x1000 and mobile 390x844, campus
synchronization, guidance/transition controls, pointer/keyboard and layout, plus
320px checks. It recorded 228 read and 39 POST requests.

Documentation local-link check passed: 11 changed documents, 113 local file links,
zero missing targets. git diff --check passed.

GitHub fast-gates passed on initial documentation commit 9379896: run 35282449100.
CI authenticated and pulled the published immutable image successfully; the local
registry limitation does not apply to that CI run. Final-head CI is required before merge.

Local gates:

| Gate | Result |
| --- | --- |
| Full package pytest | 617 passed, 16 skipped, 86.25% coverage; first run 259.70s |
| Ruff | Exit 0; all checks passed |
| Pyright | Exit 0; zero errors/warnings/information |
| Artifact data-QA | Exit 0; 23 passed, 1 skipped, 609 deselected (9.87s) |
| Launcher collision/port contract | Exit 0 using temporary LF-normalized script copies |
| Host-Python boundary | Exit 0 |
| Rebuild launcher | Exit 0 using temporary LF-normalized script copies |

Local capture limitations: the first full pytest completed successfully internally,
but a PowerShell-expanded shell status variable made its outer log-capture wrapper
return 1 (`Illegal number`). A corrective capture was started; its final log is
retained in dt024-test.log: it independently completed with 617 passed, 16 skipped and 86.25% coverage in 252.14s. The first run summary is dt024-test-summary.log. This was a capture error, not a
failing pytest assertion. Shell launcher tests initially failed on Windows CRLF
copies; reruns normalized temporary script copies inside Docker without changing
repository files. Initial failure evidence is retained in dt024-launcher-sh.log.
GitHub's clean Linux checkout independently passed the unchanged shell gates.

Independent large-model judge reviewed the integrated documentation and requested
two clarifications: documentation-only authorization, and explicit supersession of
connected-destination submission/building-floor fallback. Both were applied. The
judge then APPROVED documentation content with no remaining material findings,
conditional on recording passing required checks before merge. This verdict does
not approve an implemented DT-024 UI.


Demo container ID: `a75cd93b32a524b404a61eca7da99c46222c10ecc4185822eef964d0a35bc292`.
Docker-computed accepted artifact SHA-256 values (unchanged):
- GeoPackage: `f3d3d97e7749d1606739a078195eebc736279b780cd62076e994908652e71f65`
- Graph: `ed020258ae8a39410db3f51c5e709b5bb4f8a18755c426c853635b24705d789d`
- Stats: `2a88700a7c829c0146303f258cbbc82e03541c9e8a8ab4b5731c29a300c199e1`

## Limits

Existing navigation defects are deliberately documented, not fixed in this PR.
Browser/API fixtures do not establish DT-024 usability acceptance, physical LAN
acceptance, source correctness or candidate promotion. No source-to-candidate build
was needed because no source/build/runtime changes were made. Ignored build logs and
screenshots are local evidence; durable outcomes are recorded here before merge.
