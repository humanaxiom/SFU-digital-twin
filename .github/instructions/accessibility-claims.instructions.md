---
description: "Use when writing or reviewing any code, schema, or documentation that makes an accessibility claim about a route, unit, or path. Covers the elevator-only honesty rule and provenance requirements."
applyTo: "packages/**,docs/**"
---
# Accessibility claims

- The source geodatabase has **no path-level accessibility attributes** (no width, slope, surface,
  door-power data — see [docs/01-data-findings.md gaps G1–G3](../../docs/01-data-findings.md#8-data-gaps-that-constrain-the-design)).
- The only honest accessible-routing rule this data supports is: **exclude every edge with
  `mode = stairs`; route only over pathways and `TRANSITION_TYPE = 4` (elevator) edges** — see
  [docs/02-system-design.md §4.2](../../docs/02-system-design.md#42-accessible-mode--exactly-what-it-does-and-does-not-claim).
- Never phrase an accessible route as "wheelchair-certified" or imply a stronger guarantee than
  "elevator-only, stairs excluded." Surface the `not_verified` list (`door_width`, `path_width`,
  `slope`, `powered_doors`, `surface`) alongside any accessibility claim in an API response or UI
  string.
- Any field that drives an accessibility decision must carry `verified_by` and `verified_date`.
  Unknown must never default to accessible — default to the more conservative (non-accessible)
  assumption.
- If no step-free path exists, the correct behavior is an explicit failure (e.g. HTTP 409 with
  reachable levels and nearest elevator) — never a silent fallback to a stairs route.
