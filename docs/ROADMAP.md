# Roadmap

This review checkpoint brings together the implementation, plans and local
verification evidence for the increments developed on top of `5ca5186`.

The three-building pilot supports default two-room click directions, room search,
explicit route preview,
chronological instructions, exploration and return. The
[journey report](reports/DT-024-JOURNEY.md) records Stage D and integrated
Stage E verification. The [project oral history](ORAL-HISTORY.md) traces the
source and interface decisions behind the pilot.

The current application checkpoint is `16dcde5`: [DT-034](reports/DT-034.md)
restored default click routing, [DT-036](reports/DT-036.md) accelerated complete
floor loading, [DT-037](reports/DT-037.md) bounded stalled floor requests with
Retry, and [DT-038](reports/DT-038.md) added retained-tab JavaScript update checks.
These additions preserve Preview, inspection and exploration/return. Update checks
cover JavaScript only and require one fresh load for older tabs. The
[documentation checkpoint](reports/DOCS-CHECKPOINT-20261120.md) records fresh E2E
separately from those deliveries; a GitHub push does not establish deployment.

## Rollout order

1. **Three-building navigation pilot.** Stage D delivered journey, mobile and
   scene reuse. Stage E replayed the pilot in Docker against accepted and
   candidate artifacts.
   [Navigation plan](plans/DT-024.md)
2. **Add more buildings across SFU Burnaby.** Applied Sciences Building (ASB,
   building 038) is the first footprint screened for the isolated overview.
   The [ASB intake record](reports/DT-023-ASB-INTAKE.md) distinguishes its
   public footprint from the indoor coverage of AQ, ECC and Strand Hall.
   Continue DT-023 with authoritative
   building records and explicit coverage for each addition. Admit indoor or
   interbuilding routes when the corresponding pathways, entrances and connections
   are verified. Use isolated candidates, measure coverage and run the browser and
   API checks against the exact artifacts under review.
   [Campus plan](plans/DT-023.md) · [GIS evidence request](requests/GIS-DATA-NEEDED.md)
3. **Extend to other SFU campuses after the Burnaby expansion.** Scope each
   campus with its source owner and confirm the building and floor identifiers,
   coordinate references and coverage before planning admission. Define and review
   any campus selection or data contract changes when that work is scoped.

The rollout sequence sets delivery priorities. The
[handoff](HANDOFF.md) records verified state and operational decisions. The table
below follows the broader [design phases](02-system-design.md#11-delivery-phases).

| Phase | Deliverable | Status |
| --- | --- | --- |
| 0 | Data profiling, system design, harness scaffolding | ✅ Complete |
| 1 | ETL → GeoPackage + contracted graph + build report | DT-016/033 isolated builds verified. DT-017 legacy candidate accepted for local review. Revised-source admission and artifact promotion remain open. |
| 2 | Routing core: profiles, A*, accessible invariant tests | Bounded DT-014 demo implemented; broader phase deferred |
| 3 | Turn-by-turn instruction generator | DT-018 guidance and DT-024 cover explicit Preview, chronological visits and mobile exploration/return on the pilot. See the journey report for gate status. |
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
