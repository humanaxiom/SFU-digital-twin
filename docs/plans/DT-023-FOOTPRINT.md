# DT-023 — Applied Sciences Building footprint screen

Screen the SFU RoomFinder Building Basemap for a candidate Applied Sciences
Building footprint. DT-023 allows overview-only expansion when identity and
geometry are verified. ADR-0016 governs the running pilot. This intake produces
review evidence while source admission and application delivery remain separate
decisions.

- Query the official production layer over HTTPS for `Abbr = 'ASB'`. Retain its
  returned identifiers, attributes, CRS and exact coordinate sequences. Reject
  ambiguity, incomplete query results and invalid geometry before recording evidence.
- Read the returned polygon using the GDAL Esri JSON driver. Use EPSG:26910 for
  bounds and area. Keep the native response alongside the checked projection in
  the evidence and hash their canonical JSON representations.
- Use the immutable inputs and running artifacts as-is. Run intake in a disposable
  Docker container with read-only program files and a dedicated experiment output
  mount. Reserve a fresh output name for each run.
- Demonstrate Docker RED before implementing the intake. Verify one acceptable
  polygon and rejection of ambiguous, incomplete and invalid responses with
  offline fixtures. Replay the complete HTTPS-to-evidence workflow in Docker and
  record the command, image, exit and evidence hash.
- Confirm any authoritative facility and floor/room joins with Facilities and GIS
  before indoor admission. Footprint evidence supports only overview review. Source
  coverage for entrances, walkable connections and routes requires separate evidence.

## Standalone overview review

Generate a local SVG inside offline Docker from the canonical AQ, ECC and Strand
Hall facility polygons and the isolated ASB screen. Pin both inputs. Preserve
polygon parts and holes at a uniform metric scale, label ASB building number 038,
and distinguish its footprint-only coverage from pilot indoor data. Check the
generated SVG in real Chromium. Keep outputs under ignored `build/experiments`.
