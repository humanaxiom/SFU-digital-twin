#!/usr/bin/env python3
"""Evaluate two verified experimental builds in Docker; never promote artifacts."""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
from pathlib import Path

from osgeo import ogr
from wayfinding.demo.routing import RoutingService
from wayfinding.etl import rebuild
from wayfinding.etl.build_semantics import compare_snapshots


def audit_source_slices(path: Path) -> dict:
    """Independently check audited raw pieces against immutable extracted coordinates."""
    audit = json.loads((path / "derived/topology_audit.json").read_text())
    with (path / rebuild.RAW_GRAPH).open("rb") as stream:
        graph = pickle.load(stream)  # Verified complete build ledger before loading.
    source = ogr.Open(str(path / rebuild.GPKG), 0)
    layer = source.GetLayerByName("Pathways_26910")
    physical = {}
    for _start, _end, data in graph.edges(data=True):
        physical.setdefault(data["feature_id"], []).append(data)
    feature_count = piece_count = 0
    for record in audit["features"]:
        feature = layer.GetFeature(int(record["feature_id"]))
        geometry = feature.GetGeometryRef()
        if geometry.GetGeometryName().upper().startswith("MULTI"):
            if geometry.GetGeometryCount() != 1:
                raise ValueError("Multipart feature entered exact source-slice audit")
            geometry = geometry.GetGeometryRef(0)
        points = [geometry.GetPoint(index) for index in range(geometry.GetPointCount())]
        represented = []
        total = 0.0
        for piece in record["pieces"]:
            start, end = piece["start_vertex"], piece["end_vertex"]
            if not 0 <= start < end < len(points):
                raise ValueError("Invalid forward source span")
            represented.extend(range(start, end))
            expected = points[start:end + 1]
            edges = physical.get(piece["physical_id"], [])
            if len(edges) != 2:
                raise ValueError("Source piece must retain exactly two directed arcs")
            actual = [list(edge["geometry"].coords) for edge in edges]
            if expected not in actual or list(reversed(expected)) not in actual:
                raise ValueError("Raw piece differs from exact directed source slice")
            if any(not math.isclose(edge["length_3d"], piece["length_3d"], rel_tol=1e-12)
                   for edge in edges):
                raise ValueError("Directed piece weight differs from audit")
            total += piece["length_3d"]
            piece_count += 1
        if represented != list(range(len(points) - 1)):
            raise ValueError("Source segments were omitted, duplicated or reordered")
        authoritative_length = feature.GetField("LENGTH_3D")
        if (
            isinstance(authoritative_length, bool)
            or not isinstance(authoritative_length, (float, int))
            or not math.isfinite(authoritative_length)
            or authoritative_length <= 0
        ):
            raise ValueError("Source feature has invalid authoritative length")
        if not math.isclose(
            record["source_length_3d"], authoritative_length, rel_tol=1e-12, abs_tol=1e-9
        ):
            raise ValueError("Topology audit differs from authoritative source length")
        if not math.isclose(total, authoritative_length, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("Split pieces do not conserve authoritative source length")
        feature_count += 1
    return {"status": "passed", "features": feature_count, "physical_pieces": piece_count,
            "checks": ["exact source coordinate slices", "forward/reverse arcs",
                       "ordered source segment coverage", "authoritative length conservation"]}


def main() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run this evaluation in Docker")
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", default="dt022.json")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.json", args.output):
        raise ValueError("Output must be a simple JSON filename")
    baseline_path, baseline_manifest = rebuild._load(args.baseline, "complete")
    candidate_path, candidate_manifest = rebuild._load(args.candidate, "complete")
    for manifest, expected in ((baseline_manifest, "endpoint-v1"),
                               (candidate_manifest, "exact-shared-vertices-v1")):
        if manifest.get("build_config", {}).get("topology_mode") != expected:
            raise ValueError(f"Expected sealed topology mode {expected}")
    if baseline_manifest["source"] != candidate_manifest["source"]:
        raise ValueError("Comparison source identities differ")

    def service(path: Path) -> RoutingService:
        return RoutingService.from_artifacts(
            path / rebuild.GPKG, path / rebuild.CONTRACTED, path / rebuild.STATS,
        )

    baseline, candidate = service(baseline_path), service(candidate_path)
    snapshots = [json.loads((path / rebuild.SEMANTICS).read_text())
                 for path in (baseline_path, candidate_path)]
    report = {
        "version": "dt022-candidate-evaluation-v1",
        "baseline_run": args.baseline,
        "candidate_run": args.candidate,
        "baseline_manifest_sha256": baseline_manifest["manifest_sha256"],
        "candidate_manifest_sha256": candidate_manifest["manifest_sha256"],
        "comparison": compare_snapshots(*snapshots),
        "source_slice_audit": audit_source_slices(candidate_path),
        "profiles": [{profile: {key: value for key, value in metrics.items() if key != "groups"}
                      for profile, metrics in snapshot["profiles"].items()}
                     for snapshot in snapshots],
        "availability": [],
        "fixtures": [],
        "promotion": "not_promoted",
    }
    fixtures = report["fixtures"]

    def add_fixture(name: str, origin_id: str, destination_id: str, profile: str,
                    *, gained: bool = False) -> None:
        actual = candidate.route(origin_id, destination_id, profile)
        previous = baseline.route(origin_id, destination_id, profile)
        if gained and (previous["status"] != 409 or actual["status"] != 200):
            raise ValueError(
                f"Claimed gained route {name} changed {previous['status']} -> {actual['status']}, "
                "expected 409 -> 200"
            )
        fixtures.append({
            "name": name,
            "origin": {"unit_id": origin_id,
                       "room_id": candidate.endpoint_catalog[origin_id]["room_id"]},
            "destination": {"unit_id": destination_id,
                            "room_id": candidate.endpoint_catalog[destination_id]["room_id"]},
            "profile": profile,
            "gained": gained,
            "baseline_status": previous["status"],
            "baseline_distance_m": previous.get("network_distance_m"),
            "response": actual,
        })

    origin_id = "SFU_BURNABY_QUAD_6000_6071"
    origin = candidate.endpoint_catalog[origin_id]
    for profile in ("default", "elevator_only"):
        before = baseline.route_options(origin_id, profile)
        after = candidate.route_options(origin_id, profile)
        report["availability"].append({
            "origin_unit_id": origin_id, "profile": profile,
            "baseline_connected_count": before["counts"]["connected"],
            "baseline_response": before, "response": after,
        })
        previous_ids = {item["unit_id"] for item in before["destinations"]
                        if item["availability"] in ("connected", "same_anchor")}
        gained_ids = [item["unit_id"] for item in after["destinations"]
                      if item["availability"] == "connected" and item["unit_id"] not in previous_ids]
        # Prefer a meaningful same-floor span and, when supported, a floor change.
        for category, same_floor in (("same_floor", True), ("cross_floor", False)):
            choices = [unit_id for unit_id in gained_ids
                       if (candidate.endpoint_catalog[unit_id]["level_id"] == origin["level_id"])
                       == same_floor]
            if choices:
                def distance_squared(unit_id: str) -> float:
                    node = candidate.endpoint_catalog[unit_id]["anchor_node"]
                    anchor = origin["anchor_node"]
                    return sum((node[index] - anchor[index]) ** 2 for index in (0, 1))
                destination_id = min(choices, key=lambda item: (-distance_squared(item), item))
                add_fixture(f"aq6071_gained_{category}_{profile}", origin_id,
                            destination_id, profile, gained=True)
        add_fixture(f"aq6071_original_{profile}", origin_id,
                    "SFU_BURNABY_QUAD_6000_6067", profile)

    canonical = json.loads((rebuild.REPO_ROOT / "docs/reports/DT-015-demo-routes.json").read_text())
    for name, fixture in canonical["fixtures"].items():
        add_fixture(name, fixture["origin"]["unit_id"], fixture["destination"]["unit_id"],
                    fixture["profile"])
    add_fixture("aq303_camera", "SFU_BURNABY_QUAD_3000_303",
                "SFU_BURNABY_QUAD_3000_3149", "default")
    folder = rebuild.EXPERIMENTS_ROOT / "evaluations"
    rebuild._no_symlinks(folder)
    folder.mkdir(exist_ok=True)
    output = folder / args.output
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "comparison": report["comparison"]["profiles"],
                      "aq6071": [{"profile": item["profile"],
                                  "before": item["baseline_connected_count"],
                                  "after": item["response"]["counts"]["connected"]}
                                 for item in report["availability"]],
                      "fixtures": [{"name": item["name"], "status": item["response"]["status"],
                                    "gained": item["gained"]} for item in fixtures]}, indent=2))


if __name__ == "__main__":
    main()
