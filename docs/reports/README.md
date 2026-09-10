# Reports

Generated build/test/data-QA reports explicitly required as durable ticket evidence land here.
DT-009 owns the final `build-report.json`, including the verified source GDB directory hash,
intermediate/final artifact hashes, image and ETL versions, and validation counts.

Binary and working artifacts (`*.pkl`, GeoPackages, temporary stats, caches, local QA output) remain
ignored under `build/` and are regenerated through checked-in container targets. Raw Phase 0 source
profiling evidence remains under [docs/generated/](../generated); it is not part of the Phase 1
artifact-lineage chain. See ADR-0006.
