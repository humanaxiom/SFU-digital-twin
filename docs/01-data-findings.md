# Data Findings — `IndoorWayfinding.gdb`

Source (read-only, never modified): `C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb`

Reproduce everything in this document with:

```powershell
.\tools\dump_gdb_schema.ps1     # offline schema read (no Docker)
.\tools\dump_gdb_domains.ps1    # coded-value domains (no Docker)
.\tools\run_profile.ps1         # full GDAL profile (Docker)
```

Raw outputs land in [docs/generated](generated).

---

## 1. Format and provenance

| Property | Value |
| --- | --- |
| Format | Esri File Geodatabase (OpenFileGDB driver reads it fine) |
| Information model | **Esri ArcGIS Indoors Information Model (AIIM)** — `Facilities` / `Levels` / `Units` / `Details` / `Pathways` / `Transitions` / `Landmarks` |
| CRS | **EPSG:26910** (NAD83 / UTM zone 10N), metres |
| Dimensionality | All layers 3D (`hasZ=true`) |
| Extent | ~272 m × 179 m (505981–506254 E, 5458380–5458560 N) |

Because it is AIIM, the data is already shaped for routing — this is the single most important finding. We do **not** need to derive a network from floor-plan linework; a pathway network already exists.

## 2. Layer inventory

| Layer | Geometry | Features | Role in the system |
| --- | --- | --- | --- |
| `Facilities_AQ_SH_ECC` | 3D MultiPolygon | 3 | Building footprints |
| `Levels_AQ_SH_ECC` | 3D MultiPolygon | 11 | Floor plates / floor picker |
| `Units_AQ_SH_ECC` | 3D MultiPolygon | 1,210 | Rooms — the searchable destination catalogue |
| `Details_AQ_SH_ECC` | 3D MultiLineString | 55,593 | Walls, glazing, doors — basemap rendering only |
| `Pathways_AQ_SH_ECC` | 3D MultiLineString | 22,426 | **Horizontal routing network** |
| `Transitions_AQ_SH_ECC` | 3D MultiLineString | 63 | **Vertical routing network** (stairs / elevators) |
| `Landmarks_AQ_SH_ECC` | 3D Point | 41 | Amenity POIs + turn-by-turn reference cues |
| `Landmarks_..._ATTACH` | table | — | Attachment blobs (photos) for landmarks |

## 3. Facilities and levels

Three connected buildings on SFU Burnaby:

| `FACILITY_ID` | `NAME` | `NAME_LONG` |
| --- | --- | --- |
| `SFU_BURNABY_QUAD` | AQ | Academic Quadrangle |
| `SFU_BURNABY_ECC` | ECC | East Concourse Cafeteria |
| `SFU_BURNABY_STRAND` | SH | Strand Hall |

`LEVELS_ABOVE_GROUND` is **null for all three facilities** — do not rely on it.

`VERTICAL_ORDER` is the campus-wide floor alignment key and is what makes cross-building routing possible. `LEVEL_NUMBER` is per-building and is *not* comparable across facilities:

| `VERTICAL_ORDER` | AQ | SH | ECC |
| --- | --- | --- | --- |
| -2 | 1000 | | |
| -1 | 2000 | 100 | |
| 0 | 3000 | 1000 | 3000 |
| 1 | 4000 | 2000 | |
| 2 | 5000 | 3000 | |
| 3 | 6000 | | |

**Design consequence:** the floor picker must be driven by `VERTICAL_ORDER`, with per-facility labels from `NAME_SHORT`. Selecting "ground level" shows AQ 3000 + SH 1000 + ECC 3000 simultaneously.

## 4. Units (the destination catalogue)

- 1,210 units; `NAME`, `NAME_LONG`, `ROOM_ID` are **100 % populated** (no nulls).
- `SEARCHABLE`: `Y` = 1,017, `N` = 193 — a curated public/private flag that the search index must honour.
- `ROOM_ID` is the human-facing key users actually type: `AQ1004`, `AQ6126C`, `SH227`.
- `NAME_LONG` format is `"<room>, <level>"` (e.g. `1004, 1000`) — weak for search; `ROOM_ID` plus `USE_TYPE` is the better index.

Per-level distribution (total / searchable): AQ6000 279/263, AQ3000 197/161, AQ5000 172/151, SH3000 146/136, SH2000 116/109, AQ2000 113/73, SH1000 79/65, AQ1000 37/18, ECC3000 33/18, AQ4000 30/20, SH100 8/3.

Top `USE_TYPE` values (39 distinct): Office 539, Corridor 104, Research Laboratory 55, Stairs 54, Classroom 39, Meeting Room 30, Elevator Shaft 30, General Storage 28, Mechanical Room 20, Electrical Room 17.

**Accessibility-relevant `USE_TYPE` values exist as free text**, e.g.
`Washroom, single-stall, accessible` (15), `Washroom, men's, accessible` (12), `Washroom, women's, accessible` (11).
These are the only explicit accessibility signals anywhere in the dataset, and they describe destinations — not the path.

`CAPACITY`, `AREA_ID`, `AREA_GROSS`, `HEIGHT_RELATIVE`, `SCHEDULE_EMAIL`, `ASSIGNMENT_TYPE`, `RESERVATION_METHOD` exist. Room-booking features are possible later but are out of scope for navigation.

> Note: the raw XML in `GDB_Items` misaligns the `DomainName` tags for `Units` (it attaches `DOM_ASSIGNMENT_TYPE` to `CAPACITY`). `ogrinfo` is authoritative: `ASSIGNMENT_TYPE` → `DOM_ASSIGNMENT_TYPE`, `RESERVATION_METHOD` → `DOM_RESERVATION_METHOD`.

## 5. Routing network

### Pathways (22,426 features)

| Field | Finding |
| --- | --- |
| `PATHWAY_TYPE` | **`1` (Hallway / Sidewalk) for every feature** |
| `PATHWAY_RANK` | `1` Primary = 13,108; `2` Secondary = 9,318 |
| `TRAVEL_DIRECTION` | **`1` (Both directions allowed) for every feature** → the graph is undirected |
| `LENGTH_3D` | 100 % populated → use directly as edge weight |
| `DELAY` | **99.5 % null** (22,314 of 22,426) → unusable as a cost term |
| `LEVEL_ID` | 100 % populated |

Segment geometry statistics: min 0.002 m, **mean 0.94 m**, max 150.9 m, total 21,088 m.

**Design consequence:** the network is extremely over-noded — 22k segments averaging under a metre. Routing directly on raw segments is wasteful and produces unusable instruction output (thousands of micro-steps). The ETL **must** contract degree-2 chains into single edges before instruction generation.

### Transitions (63 features)

| `TRANSITION_TYPE` | Meaning (`DOM_NETWORK_TYPE`) | Count |
| --- | --- | --- |
| `2` | Stairs / Curb | **42** |
| `4` | Elevator / Wheelchair Lift | **21** |

All are `TRANSITION_RANK = 1` and `TRAVEL_DIRECTION = 1` (bidirectional). `LENGTH_3D`, `HEIGHT_FROM`, `HEIGHT_TO` are 100 % populated. `VERTICAL_ORDER_FROM` / `_TO` are adjacent in every case except two elevator features that span `0 → 2` (express elevator).

**No escalators (type 5), no ramps (type 3), no moving walkways (type 6) exist in this dataset.**

**This is the accessibility mechanism.** The only lever the data gives us for an accessible route is: exclude `TRANSITION_TYPE = 2` and keep `TRANSITION_TYPE = 4`. With 21 elevator transitions across 11 levels, an accessible route is feasible but the network is thin — connectivity must be validated per level pair.

### Coded-value domains (verbatim from the GDB)

```
DOM_NETWORK_TYPE   1 Hallway / Sidewalk   2 Stairs / Curb   3 Ramp / Curb Ramp
                   4 Elevator / Wheelchair Lift   5 Escalator   6 Moving Walkway
DOM_NETWORK_RANK   1 Primary   2 Secondary   3 Tertiary
DOM_TRAVEL_DIRECTION  1 Both Directions Allowed  2 From-To Allowed  3 To-From Allowed
DOM_RESERVATION_METHOD 0 Not reservable  1 Reservable
DOM_ASSIGNMENT_TYPE   hotdesk | hotel | none | not assignable | office
```

## 6. Details (basemap linework)

55,593 features, `USE_TYPE` codes: `AGL` 32,974 (glazing), `AWA` 11,002 (wall), **`ADO` 6,865 (door)**, `AWAFU` 4,547, `AWAMO` 196, `AWACO` 9.

The 6,865 `ADO` door lines are the only door representation. They carry no width, swing, or powered-operator attribute, so they cannot support door-level accessibility checks — but they *can* be used to place "go through the doors" instructions by intersecting a route with door lines.

## 7. Landmarks

41 points, two amenity classes encoded only in free-text `DESCRIPTION`:

- `Water Fountain near AQ 6028C`, `Water Fountain near SH 227`, …
- `Vending Machine close to Room 2013.4`, `Vending Machine near East Cafeteria`, …

**There are duplicates**: "Vending Machine close to B9201" appears 5×, "…close to Room 2013.4" appears 5×. Deduplicate on `(DESCRIPTION, LEVEL_ID)` plus a spatial tolerance during ETL.

There is no `NAME`, no category field, and no `LANDMARK_TYPE`. Category must be parsed from `DESCRIPTION` (`^(Water Fountain|Vending Machine)`) during ETL — a fragile but tractable rule for 41 rows.

---

## 8. Data gaps that constrain the design

| # | Gap | Impact | Mitigation |
| --- | --- | --- | --- |
| G1 | No accessibility attributes on `Pathways` (no width, slope, surface) | Cannot certify a path as wheelchair-passable | Model accessibility purely as *vertical-transition mode exclusion*; state this limitation in the UI |
| G2 | No ramp or escalator features | Cannot offer step-free alternatives other than elevators | Accessible profile = elevators only; fail loudly when no elevator path exists |
| G3 | No door width / powered-door attributes on `ADO` | Cannot warn about heavy or narrow doors | Out of scope; flag as a future survey task |
| G4 | `DELAY` 99.5 % null | No congestion/wait modelling from data | Use a configurable static elevator wait constant instead |
| G5 | `LEVELS_ABOVE_GROUND` null on all facilities | Cannot infer ground floor | Derive ground floor as `VERTICAL_ORDER = 0` (verified consistent here) |
| G6 | No positioning infrastructure data (no BLE beacons, no Wi-Fi APs, no QR anchors) | No blue-dot / live turn-by-turn | Ship "pick your start" + QR-anchored origin; design the API so a position provider can be added later |
| G7 | Landmark categories and duplicates are unmodelled | Noisy POI layer | Normalise in ETL; do not push raw `DESCRIPTION` to the LLM |
| G8 | Only 3 buildings | Not campus-wide | ETL must be facility-agnostic so more AIIM extracts drop in unchanged |
| G9 | No opening hours, no room booking state, no closure/maintenance feed | Routes may send users through locked doors | Design a `restrictions` overlay table the ETL merges in, populated later |

## 9. What this means for the build

1. The network is **usable as-is** for shortest-path routing after node-snapping and degree-2 contraction.
2. **Accessibility is a first-class routing profile**, implemented as a transition-type filter — and it is the *only* honest accessibility claim this data supports.
3. **Turn-by-turn must be generated geometrically** (bearing deltas on contracted edges) because the data carries no instruction hints.
4. Search quality rests on `ROOM_ID` + `USE_TYPE` + level context, filtered by `SEARCHABLE = 'Y'`.
5. `VERTICAL_ORDER` — not `LEVEL_NUMBER` — is the cross-building floor key.
