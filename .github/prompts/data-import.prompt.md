---
description: "Run or extend the ETL against the read-only source geodatabase, always through checked-in, reproducible scripts — never an ad hoc one-off command"
argument-hint: "<what changed in the ETL, or which layer/mapping to add>"
agent: agent
---
Handle an ETL change for: ${input:change:What ETL step or mapping is changing}

1. Confirm the change is expressed as a plan (`planner`) before any script is written or edited —
   ETL changes affect reproducibility guarantees and almost always warrant an ADR
   (`architect`) if they touch the `facility`/`level`/`unit`/`landmark` schema or the graph-build
   steps in [docs/02-system-design.md §3](../../docs/02-system-design.md#3-etl-pipeline).
2. Every step must run inside a container against the read-only-mounted source GDB — never touch
   `C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb` directly, and never require host
   Python/GDAL. Follow the existing pattern in `tools/run_profile.ps1`.
3. After `implementer` writes the ETL step, invoke `data-qa` to validate the invariants in
   [docs/01-data-findings.md §8](../../docs/01-data-findings.md#8-data-gaps-that-constrain-the-design)
   and [docs/02-system-design.md §3.3 step 6](../../docs/02-system-design.md#3-etl-pipeline)
   (connectivity, orphan units, `vertical_order` mapping).
4. Any fixture/golden capture must be its own checked-in script invocation (e.g. a `make` target),
   never a throwaway command — this is Prime Directive 5.
5. Finish through the normal `judge` → `doc-writer` steps before considering the change done.
