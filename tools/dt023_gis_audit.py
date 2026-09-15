#!/usr/bin/env python3
"""Read-only DT-023 coverage and literal source-vertex evidence; run in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path

import networkx as nx
from osgeo import ogr
from wayfinding.demo.routing import RoutingService


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def facility_catalog(gpkg):
    dataset = ogr.Open(str(gpkg), 0)
    facilities = sorted(f.GetField("facility_id")
                        for f in dataset.GetLayerByName("facility_26910"))
    levels = {f.GetField("level_id"): f.GetField("facility_id")
              for f in dataset.GetLayerByName("level_26910")}
    if any(facility not in facilities for facility in levels.values()):
        raise ValueError("Level references an unknown facility")
    return facilities, levels


def coverage(folder):
    gpkg, graph, stats = [folder / name for name in
                          ("wayfinding.gpkg", "graph_contracted.pkl", "graph_contracted_stats.json")]
    service = RoutingService.from_artifacts(gpkg, graph, stats)
    facilities, levels = facility_catalog(gpkg)
    groups = {facility: [] for facility in facilities}
    for endpoint in service.endpoint_catalog.values():
        if endpoint["level_id"] not in levels:
            raise ValueError("Endpoint references an unknown level")
        groups[levels[endpoint["level_id"]]].append(endpoint)
    rows = []
    for profile, modes in service.allowed_modes.items():
        filtered = nx.DiGraph()
        filtered.add_nodes_from(service.graph)
        filtered.add_edges_from((u, v) for u, v, data in service.graph.edges(data=True)
                                if data["mode"] in modes)
        reachable = {}
        for origin in sorted(groups):
            for destination in sorted(groups):
                counts = dict.fromkeys(("connected", "same_anchor", "disconnected",
                                        "endpoint_unavailable"), 0)
                fixture = None
                for start in groups[origin]:
                    for end in groups[destination]:
                        if start["unit_id"] == end["unit_id"]:
                            continue
                        if not start["eligible"] or not end["eligible"]:
                            counts["endpoint_unavailable"] += 1
                            continue
                        anchor = start["anchor_node"]
                        if end["anchor_node"] == anchor:
                            counts["same_anchor"] += 1
                            continue
                        if anchor not in reachable:
                            reachable[anchor] = nx.descendants(filtered, anchor) | {anchor}
                        if end["anchor_node"] in reachable[anchor]:
                            counts["connected"] += 1
                            if fixture is None:
                                fixture = [start["unit_id"], end["unit_id"]]
                        else:
                            counts["disconnected"] += 1
                total = len(groups[origin]) * (len(groups[destination]) - (origin == destination))
                assert sum(counts.values()) == total
                status = ("unavailable" if not groups[origin] or not groups[destination] else
                          "mapped_route" if counts["connected"] else
                          "disconnected" if counts["disconnected"] else "partial_source_coverage")
                rows.append({"profile": profile, "origin": origin, "destination": destination,
                             "total_ordered_pairs": total, **counts,
                             "eligible_ordered_pairs": total - counts["endpoint_unavailable"],
                             "reachable_ordered_pairs": counts["connected"] + counts["same_anchor"],
                             "status": status,
                             "fixture": fixture})
    return {"artifacts": {str(p): digest(p) for p in (gpkg, graph, stats)},
            "units": {key: {"catalog": len(value), "eligible": sum(e["eligible"] for e in value)}
                      for key, value in sorted(groups.items())}, "rows": rows}


def source_audit(path):
    source = ogr.Open(str(path), 0)
    if source is None:
        raise ValueError("Cannot open revised source read-only")
    layer = source.GetLayerByName("Pathways_AQ_SH_ECC_Revised")
    known = defaultdict(set)
    additions = []
    for feature in layer:
        geom = feature.GetGeometryRef()
        parts = [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
        lines = [[part.GetPoint(i) for i in range(part.GetPointCount())] for part in parts]
        record = {"fid": feature.GetFID(), "facility": feature.GetField("FACILITY_ID"),
                  "level": feature.GetField("LEVEL_ID"), "vertical_order": feature.GetField("VERTICAL_ORDER"),
                  "length_3d": feature.GetField("LENGTH_3D"), "lines": lines}
        if feature.GetFID() > 22426:
            additions.append(record)
        else:
            for line in lines:
                for vertex in line:
                    known[vertex].add((record["fid"], record["facility"], record["level"]))
    literal = nx.Graph()
    endpoints = []
    for record in additions:
        for line in record["lines"]:
            literal.add_edges_from(pairwise(line))
            for index in (0, len(line) - 1):
                if line[index] in known:
                    endpoints.append({"fid": record["fid"], "endpoint_index": index,
                                      "xyz": line[index], "known": sorted(known[line[index]])})
    components = []
    for vertices in nx.connected_components(literal):
        contacts = {item for vertex in vertices for item in known.get(vertex, ())}
        components.append({"vertices": len(vertices), "facilities": sorted({x[1] for x in contacts}),
                           "contacts": sorted(contacts)})
    components.sort(key=lambda item: (-item["vertices"], item["facilities"]))
    return {"source_files_sha256": {p.name: digest(p) for p in sorted(path.iterdir()) if p.is_file()},
            "crs": layer.GetSpatialRef().ExportToWkt(), "feature_count": len(additions),
            "null_facility": sum(r["facility"] is None for r in additions),
            "null_level": sum(r["level"] is None for r in additions),
            "vertical_order": dict(Counter(r["vertical_order"] for r in additions)),
            "length_3d_m": sum(r["length_3d"] for r in additions),
            "with_zero_z": sum(any(p[2] == 0 for line in r["lines"] for p in line) for r in additions),
            "multipart": [r["fid"] for r in additions if len(r["lines"]) != 1],
            "exact_endpoint_contacts": endpoints, "literal_xyz_components": components,
            "admission": "excluded; literal XYZ adjacency is evidence, not verified grade or portal topology"}


def main():
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", default="/source.gdb", type=Path)
    args = parser.parse_args()
    root = Path("/workspace")
    report = {"version": "dt023-gis-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "code_sha256": {str(p.relative_to(root)): digest(p) for p in sorted(
                  [root / "tools/dt023_gis_audit.py",
                   *root.glob("packages/wayfinding/src/wayfinding/**/*.py")])},
              "snapshot_status": {"accepted": "accepted legacy artifacts",
                                  "candidate": "dt022-exact-final3; unpromoted"},
              "accepted": coverage(Path("/workspace/build")),
              "candidate": coverage(Path("/workspace/build/experiments/dt022-exact-final3/derived")),
              "revised_source": source_audit(args.source)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "sha256": digest(args.output)}))


if __name__ == "__main__":
    main()
