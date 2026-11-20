# 26. Isolated Burnaby overview with a reviewed public footprint

Status: accepted for the optional local ASB preview.

The indoor artifact contains three Burnaby facilities. SFU Facilities and the
SFU Room Finder Building Basemap also identify Applied Sciences Building as
ASB, building 038. The Building Basemap supplies a polygon. The current indoor
snapshot supplies no corresponding ASB levels, rooms or pathways.

Extend [ADR-0016](0016-campus-overview-and-coverage.md) for an isolated preview.
The ordinary demo continues to return its existing three-building response.
A separate launch may supply a trusted local footprint screen using
`--overview-footprint`. Validate its recorded digest, source, identity, scope,
projected CRS and geometry before starting. The resulting campus response
uses scope `burnaby-overview-preview`, retains incomplete inventory status,
and includes per-feature source provenance for ASB. Keep the base GeoPackage
and graph read-only. The service requires no external network requests.

Use `ROOMFINDER_BURNABY_038` as the overview feature ID. It identifies a
Room Finder building and carries no assumption about a future indoor facility
key. List ASB in the campus and building selectors, show its footprint and
declare its coverage `overview_only`. Its level list and verified entrance
list are empty. In a selected ASB view, floor and room routing controls must
accurately reflect available coverage. ASB selection alone preserves any
existing route draft and committed route. Source-backed indoor or outdoor
links and further buildings have separate admission records.
