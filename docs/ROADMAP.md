# Roadmap

Next client increment: **[DT-024 navigation overhaul](plans/DT-024.md)**, architecture and implementation plan accepted; runtime implementation not started. [ADR-0017](adr/0017-navigation-state-and-journey.md) defines its contract. This improves the existing SVG demo and does not complete the future MapLibre phase or promote routing data.

Tracks the delivery phases in
[docs/02-system-design.md §11](02-system-design.md#11-delivery-phases) against actual status. Kept
in sync by `doc-writer` after every `judge` APPROVE; the authoritative narrative state lives in
[docs/HANDOFF.md](HANDOFF.md) — this file is the at-a-glance table.

| Phase | Deliverable | Status |
| --- | --- | --- |
| 0 | Data profiling, system design, harness scaffolding | ✅ Complete |
| 1 | ETL → GeoPackage + contracted graph + build report | DT-016 isolated rebuild/source review implemented; DT-017 geometry/source reconciliation next; production promotion open |
| 2 | Routing core: profiles, A*, accessible invariant tests | Bounded DT-014 demo implemented; broader phase deferred |
| 3 | Turn-by-turn instruction generator | DT-018 local guidance/UI verified with fresh browser E2E; DT-017 geometry-quality correction remains separate |
| 4 | FastAPI service + search index + tiles | Not started |
| 5 | MapLibre web client with floor picker and accessible toggle | Not started |
| 6 | Assistant orchestrator, tool schemas, guardrails, eval suite | Not started |
| 7 | QR anchor origins; hooks for a future positioning provider | Not started |

Current plans: [DT-016](plans/DT-016.md), [DT-017](plans/DT-017.md),
[DT-018 route UI](plans/DT-018.md), and
[DT-023 campus overview/interbuilding routing](plans/DT-023.md).
DT-023 Stage 0 coverage audit and bounded Stage 1 overview passed fresh Docker
gates and candidate/accepted browser/API E2E. Remaining Stage 0 GIS reconciliation, outdoor
routing and campus expansion remain open.
Follow the shared plan → RED → implementation → gates → review workflow in AGENTS.md.
