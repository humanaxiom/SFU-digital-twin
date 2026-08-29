---
description: "Use when writing or reviewing ETL, graph-construction, or routing code that touches the AIIM geodatabase layers (Facilities/Levels/Units/Pathways/Transitions/Landmarks). Covers vertical_order, graph contraction, and connectivity invariants."
applyTo: "packages/**"
---
# Spatial data invariants

- `VERTICAL_ORDER` — not `LEVEL_NUMBER` — is the cross-building floor key
  ([docs/01-data-findings.md §3](../../docs/01-data-findings.md#3-facilities-and-levels)).
  `LEVEL_NUMBER` is per-building and not comparable across facilities.
- All computation of length, bearing, or snapping must happen in the native CRS, **EPSG:26910**.
  Reproject to EPSG:4326 only for the web-client display copy; never compute distance in 4326.
- The raw pathway network is extremely over-noded (22,426 segments, mean length 0.94 m). Degree-2
  chains must be contracted before instruction generation, or the output is thousands of useless
  micro-steps.
- A disconnected graph for the `default` routing profile is a hard build failure. A disconnected
  graph for the `accessible` profile is a warning plus an explicit reachability matrix — it is not
  an error, because 21 elevator transitions across 11 levels is genuinely thin coverage.
- Every searchable unit (`SEARCHABLE = 'Y'`) must have a zero-cost connector edge to the nearest
  pathway node on its own `level_id`; an orphan searchable unit is a data-QA failure.
- `DELAY` is 99.5% null and must not be used as a cost term; elevator wait is a configuration
  constant, documented as such.
