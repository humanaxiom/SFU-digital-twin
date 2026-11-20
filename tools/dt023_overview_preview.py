#!/usr/bin/env python3
"""Render the isolated DT-023 four-building review map inside offline Docker."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

from osgeo import ogr
from wayfinding.overview_footprint import validate_screen

CANONICAL = (
    ("SFU_BURNABY_QUAD", "AQ"),
    ("SFU_BURNABY_ECC", "ECC"),
    ("SFU_BURNABY_STRAND", "SH"),
)


def check_polygon(geometry):
    if (
        geometry is None
        or geometry.GetGeometryName() not in ("POLYGON", "MULTIPOLYGON")
        or geometry.IsEmpty()
        or not all(map(math.isfinite, geometry.GetEnvelope()))
        or not geometry.IsValid()
        or geometry.GetArea() <= 0
    ):
        raise ValueError("Expected a valid, nonempty facility polygon")


def read_canonical(path, expected_hash):
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != expected_hash:
            raise ValueError("Canonical GeoPackage SHA-256 does not match the supplied pin")
    dataset = ogr.Open(str(path), 0)
    layer = dataset.GetLayerByName("facility_26910") if dataset else None
    crs = layer.GetSpatialRef() if layer else None
    if crs is None or (crs.GetAuthorityName(None), crs.GetAuthorityCode(None)) != ("EPSG", "26910"):
        raise ValueError("Canonical facility layer must use EPSG:26910")
    facilities = {}
    for feature in layer:
        identity = (feature.GetField("facility_id"), feature.GetField("code"))
        if identity not in CANONICAL or identity in facilities:
            raise ValueError("Unexpected or duplicate canonical facility identity")
        geometry = feature.GetGeometryRef()
        check_polygon(geometry)
        facilities[identity] = (identity[1], feature.GetField("name"), geometry.Clone())
    if set(facilities) != set(CANONICAL):
        raise ValueError("Canonical facility layer must contain exactly AQ, ECC and Strand Hall")
    return [facilities[key] for key in CANONICAL]


def read_asb(path, expected_hash):
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or evidence.get("screen_sha256") != expected_hash:
        raise ValueError("ASB screen SHA-256 does not match the supplied pin")
    checked = validate_screen(evidence)
    geometry = ogr.CreateGeometryFromJson(json.dumps(checked["footprint_26910"]["geometry"]))
    check_polygon(geometry)
    return geometry


def svg_path(geometry, project):
    parts = [geometry] if geometry.GetGeometryName() == "POLYGON" else geometry
    rings = []
    for polygon in parts:
        for ring in polygon:
            vertices = [
                f"{x:.9f},{y:.9f}"
                for x, y in (project(point[0], point[1]) for point in ring.GetPoints()[:-1])
            ]
            rings.append(f"M {' L '.join(vertices)} Z")
    return " ".join(rings)


def render_svg(pilot, asb):
    buildings = [*pilot, ("ASB", "Applied Sciences Building", asb)]
    envelopes = [geometry.GetEnvelope() for _, _, geometry in buildings]
    left = min(box[0] for box in envelopes)
    right = max(box[1] for box in envelopes)
    bottom = min(box[2] for box in envelopes)
    top = max(box[3] for box in envelopes)
    scale = min(780 / (right - left), 364 / (top - bottom))
    center_x = (left + right) / 2
    center_y = (bottom + top) / 2

    def project(easting, northing):
        return 480 + (easting - center_x) * scale, 329 - (northing - center_y) * scale

    paths = []
    labels = []
    for code, name, geometry in buildings:
        candidate = code == "ASB"
        building_number = ' data-building-number="038"' if candidate else ""
        detail = ", SFU building 038, footprint only" if candidate else ", pilot indoor data"
        style = "candidate" if candidate else "pilot"
        paths.append(
            f'<path class="{style}" data-building="{code}"{building_number} fill-rule="evenodd"'
            f' d="{svg_path(geometry, project)}"><title>{escape(name)}{detail}</title></path>'
        )
        position = geometry.PointOnSurface()
        x, y = project(position.GetX(), position.GetY())
        labels.append(f'<text class="label" x="{x:.3f}" y="{y:.3f}">{code}</text>')

    scale_left = 870 - 50 * scale
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640"
  viewBox="0 0 960 640" role="img" aria-labelledby="title description" xml:lang="en">
  <title id="title">SFU Burnaby building coverage review</title>
  <desc id="description">Metric map of four building footprints. Academic Quadrangle (AQ),
    East Concourse Cafeteria (ECC) and Strand Hall (SH) have pilot indoor data.
    Applied Sciences Building (ASB), SFU building 038, has footprint-only coverage.</desc>
  <style>
    text {{ font-family: system-ui, sans-serif; fill: #132c37; }}
    .secondary {{ fill: #425b62; }}
    .pilot {{ fill: #bfdce5; stroke: #25586b; stroke-width: 1.4; }}
    .candidate {{ fill: #f7d887; stroke: #865300; stroke-width: 2; stroke-dasharray: 5 3; }}
    .label {{ font-size: 15px; font-weight: 700; text-anchor: middle;
      dominant-baseline: central; paint-order: stroke fill; stroke: #fff; stroke-width: 4; }}
  </style>
  <rect width="960" height="640" fill="#fff"/>
  <text x="36" y="47" font-size="29" font-weight="700">SFU Burnaby building coverage review</text>
  <text x="37" y="76" class="secondary" font-size="16">Applied Sciences Building · ASB · SFU building 038</text>
  <rect x="36" y="105" width="888" height="446" rx="12" fill="#f4f8f8" stroke="#d2e0e1"/>
  <g>
    {"".join(paths)}
    {"".join(labels)}
  </g>
  <g aria-hidden="true" fill="#25586b">
    <text x="71" y="139" text-anchor="middle" font-size="12" font-weight="700">Grid N</text>
    <path d="M 71,146 L 78,166 L 71,162 L 64,166 Z"/>
    <text x="{(870 + scale_left) / 2:.3f}" y="521" text-anchor="middle" font-size="13">50 m</text>
    <path d="M {scale_left:.3f},526 v 6 H 870 v -6" fill="none" stroke="#25586b" stroke-width="2"/>
  </g>
  <rect class="pilot" x="38" y="570" width="19" height="14" rx="2"/>
  <text x="67" y="582" font-size="15">Pilot indoor data</text>
  <rect class="candidate" x="232" y="570" width="19" height="14" rx="2"/>
  <text x="261" y="582" font-size="15">ASB footprint only</text>
  <text x="37" y="612" class="secondary" font-size="13">
    Geometry from the canonical pilot GeoPackage and SFU Facilities Services Room Finder · EPSG:26910
  </text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="Fresh SVG file stem under /evidence")
    parser.add_argument("--canonical-sha256", required=True, help="Expected trusted GeoPackage SHA-256")
    parser.add_argument("--screen-sha256", required=True, help="Expected reviewed ASB screen SHA-256")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.run_id):
        parser.error("run ID must be 1–64 lowercase ASCII letters, digits or hyphens")
    if not all(re.fullmatch(r"[0-9a-f]{64}", seal) for seal in (args.canonical_sha256, args.screen_sha256)):
        parser.error("expected input hashes must be lowercase SHA-256 hex strings")

    output = Path("/evidence") / f"{args.run_id}.svg"
    try:
        with ogr.ExceptionMgr():
            canonical = read_canonical(Path("/input/wayfinding.gpkg"), args.canonical_sha256)
            footprint = read_asb(Path("/input/asb.json"), args.screen_sha256)
            text = render_svg(canonical, footprint)
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        parser.exit(1, f"Overview preview failed: {exc}\n")
    print(json.dumps({"output": str(output), "preview_sha256": hashlib.sha256(text.encode()).hexdigest()}))


if __name__ == "__main__":
    main()
