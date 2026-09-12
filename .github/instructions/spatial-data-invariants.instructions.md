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
- **Measured connectivity baseline** ([ADR-0005](../../docs/adr/0005-measured-connectivity-baseline-and-validation-gates.md)):
  the pathway network has 855 connected components. The pinned fixture must reproduce 816 default
  components (all transitions) and 840 elevator-only components, with at least one component bridged
  by each transition mode. DT-006 rejects regressions and no-op transition modes but does not require
  global connectivity. DT-009 maps every unit to a component for query-time no-route results.
- ADR-0008/0009 use disclosed approximate same-level anchors and explicit unattached-unit
  failures. Do not add zero-cost room connectors: room-to-anchor traversal is unverified.
- `DELAY` is 99.5% null and must not be used as a cost term; elevator wait is a configuration
  constant, documented as such.
