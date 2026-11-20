# 28. Bound and prewarm immutable floor response bytes

Status: accepted and locally verified; [DT-036 evidence](../reports/DT-036.md).
Date: 2026-11-20

## Measurement and purpose

Exact OGR filtering reduces unnecessary row materialization but leaves large AQ
floors at about 1.6 s end to visible. Parsing and browser rendering are smaller
costs. Building all 11 complete scene bodies totals about 14.6 MB. The source
artifact is trusted, immutable and identified by its startup SHA-256.

## Contract

- Own the cache in the HTTP server instance, keyed by artifact SHA-256 and exact
  level ID. Store complete encoded response bytes, including existing limitations
  and provenance, using the unchanged JSON encoding and HTTP content type.
- Bound cached payloads to 16 scenes and 32 MiB with deterministic LRU eviction.
  An oversized response remains fully available; it is simply not retained.
  Cache eviction never removes a floor or changes its response.
- Lock cache bookkeeping and deduplicate concurrent identical misses with a
  per-key future. Construct responses outside that bookkeeping lock so a slow
  miss cannot block an already cached floor. Capture one repository reference
  for the key, scene and provenance. OGR dataset handles remain local to each
  construction; no shared mutable GDAL handles or scene dictionaries are exposed
  to callers. Never hold the cache lock while writing an HTTP response.
- Cache successful responses only. A failed build remains retryable through the
  same foreground path and existing HTTP error handling. Artifact identity
  prevents reuse across repository replacement/artifact changes.
- Normal CLI startup best-effort prewarms up to the bounded recorded-floor set
  before serving requests. This trades startup work for fast fresh-page floor
  loads. A prewarm failure is logged without sensitive details and does not
  remove foreground access or prevent otherwise usable floors from serving.
  Programmatic create_server retains lazy cache construction for compatibility.
  Limit prewarm attempts to 16 even when responses fail or exceed the cache
  budget. Handle catalog enumeration failures as best-effort as well. The 32 MiB
  limit bounds retained payload bytes, not transient construction memory.
- Preserve exact geometry, feature order, fields, room selection, two-click
  routing, inspection, Preview, availability, Clear and exploration behavior.
  No browser-cache policy, API/schema, data, route algorithm or source change.

## Verification and integration

DT-036 first completes its read-filter preservation E2E. Then demonstrate cache
RED for repeated/concurrent scene construction and validate bounds, identity,
failure retry, prewarm and exact response parity. Compare all 11 decoded and
encoded HTTP scene responses and eight rendered floor signatures. Measure
startup and fresh-page latency separately. Run fresh isolated preservation E2E
before copying verified code to the live source. A final controlled app restart
and live-port rehearsal load and verify the tested Python implementation.
