# SFU Campus Map Key Plans (local reference only)

PDFs and images in this folder are official SFU reference material downloaded by hand from
CAS-gated Facilities pages. The files remain local because this GitHub repository is public. Only
this README is committed.

https://www.sfu.ca/fs/campus-maps/key-plans/burnaby-campus/

Public campus context is available from:

https://www.sfu.ca/campuses/maps-and-directions/burnaby-map.html

## Why manual, not scripted

The Facilities pages require an SFU CAS login. Do not write an importer, scraper, or CI job that
logs into CAS, and do not commit or redistribute the downloaded files without explicit permission
from their owner. A fresh checkout intentionally does not contain these optional references.

## What these are for

Visual reference only: sanity-checking building footprints, floor counts, room numbering
conventions, and demo discussion with Facilities. The local collection covers AQ levels 1000–6000,
Strand Hall levels 1000–3000, East Concourse, and campus-level context. It does not provide an ECC
floor plan.

These static files are not structured geometry and are not an ETL or routing source. Campus maps
labelled for accessibility are presentation references only; they do not establish path-level
accessibility, elevator availability, door width, slope, surface, or powered-door status. The
application's accessible profile remains elevator-only and stairs-excluded, with no stronger claim.

## Adding a file

When adding a local file, record its source in a local inventory before using it in a stakeholder
session. CAS access establishes access, not redistribution permission. Confirm presentation and
redistribution rights with Facilities before embedding any reference in a product or public deck.

## Demo use

- Use the key plans beside the generated GeoPackage or graph as a human visual cross-check.
- Clearly label them as static Facilities references, not live product layers.
- Demonstrate only deterministic outputs produced from the AIIM geodatabase.
- Record discrepancies for Facilities/GIS review instead of correcting geometry from the PDFs.
- Do not make accessibility claims from symbols or labels visible on these maps.
