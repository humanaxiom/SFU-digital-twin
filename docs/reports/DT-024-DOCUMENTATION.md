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

Validation is in progress while the documentation PR is prepared. Replace this
paragraph with final command outcomes and review verdict before merging.

## Limits

Existing navigation defects are deliberately documented, not fixed in this PR.
Browser/API fixtures do not establish DT-024 usability acceptance, physical LAN
acceptance, source correctness or candidate promotion. No source-to-candidate build
was needed because no source/build/runtime changes were made. Ignored build logs and
screenshots are local evidence; durable outcomes are recorded here before merge.
