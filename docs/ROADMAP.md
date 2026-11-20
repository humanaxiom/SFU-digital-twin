# Roadmap

This review checkpoint brings together the implementation, plans and local
verification evidence for the increments developed on top of `5ca5186`.

As of 2026-11-20 the SVG demo supports building-scoped floors, room search and explicit route preview. Stage C passed on the accepted artifacts and the isolated Strand candidate. **Next is Stage D** in the [DT-024 plan](plans/DT-024.md), followed by the integrated Stage E acceptance run. The [Preview report](reports/DT-024-PREVIEW.md) records the tested behavior. The [project oral history](ORAL-HISTORY.md) explains how the data and interface decisions developed.

Tracks the delivery phases in
[docs/02-system-design.md §11](02-system-design.md#11-delivery-phases) against actual status. Kept
in sync by `doc-writer` after every `judge` APPROVE; the authoritative narrative state lives in
[docs/HANDOFF.md](HANDOFF.md) — this file is the at-a-glance table.

| Phase | Deliverable | Status |
| --- | --- | --- |
| 0 | Data profiling, system design, harness scaffolding | ✅ Complete |
| 1 | ETL → GeoPackage + contracted graph + build report | DT-016/033 isolated builds verified. DT-017 legacy candidate accepted for local review. Revised-source admission and artifact promotion remain open. |
| 2 | Routing core: profiles, A*, accessible invariant tests | Bounded DT-014 demo implemented; broader phase deferred |
| 3 | Turn-by-turn instruction generator | DT-018 guidance and DT-024 draft/Preview verified locally. Remaining journey and mobile interactions are tracked in Stage D. |
| 4 | FastAPI service + search index + tiles | Not started |
| 5 | MapLibre web client with floor picker and accessible toggle | Not started |
| 6 | Assistant orchestrator, tool schemas, guardrails, eval suite | Not started |
| 7 | QR anchor origins; hooks for a future positioning provider | Not started |

Active and reference plans include [DT-024 navigation](plans/DT-024.md),
[DT-017 source reconciliation](plans/DT-017.md), [DT-023 campus coverage](plans/DT-023.md),
[DT-016 isolated builds](plans/DT-016.md) and [DT-018 route guidance](plans/DT-018.md).
DT-023 Stage 0 coverage audit and bounded Stage 1 overview passed fresh Docker
gates and candidate/accepted browser/API E2E. Remaining Stage 0 GIS reconciliation, outdoor
routing and campus expansion remain open.
Follow the shared plan → RED → implementation → gates → review workflow in AGENTS.md.
