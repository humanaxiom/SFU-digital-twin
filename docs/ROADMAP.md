# Roadmap

Tracks the delivery phases in
[docs/02-system-design.md §11](02-system-design.md#11-delivery-phases) against actual status. Kept
in sync by `doc-writer` after every `judge` APPROVE; the authoritative narrative state lives in
[docs/HANDOFF.md](HANDOFF.md) — this file is the at-a-glance table.

| Phase | Deliverable | Status |
| --- | --- | --- |
| 0 | Data profiling, system design, harness scaffolding | ✅ Complete |
| 1 | ETL → GeoPackage + contracted graph + build report | Foundation complete (DT-001: package skeleton, Docker test service, Makefile gates, ADR-0002); ETL implementation not started |
| 2 | Routing core: profiles, A*, accessible invariant tests | Not started |
| 3 | Turn-by-turn instruction generator | Not started |
| 4 | FastAPI service + search index + tiles | Not started |
| 5 | MapLibre web client with floor picker and accessible toggle | Not started |
| 6 | Assistant orchestrator, tool schemas, guardrails, eval suite | Not started |
| 7 | QR anchor origins; hooks for a future positioning provider | Not started |

Decompose the next phase into tickets with `/sprint-plan`; deliver each ticket with `/tdd-feature`.
