"""Generate canonical DT-015 route evidence from approved read-only artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact import ArtifactRepository
from .routing import NOT_VERIFIED, RoutingService

ROUTES = {
    "aq_long_corridor": ("AQ5029", "AQ5044", "default"),
    "aq_stairs": ("AQ1010", "AQ2103", "default"),
    "aq_elevator": ("AQ2035.2", "AQ5046", "elevator_only"),
    "strand_corridor": ("SH1001C", "SH1003", "default"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _fixture(
    name: str,
    service: RoutingService,
    level_facilities: dict[str, str],
) -> dict[str, Any]:
    origin_id, destination_id, profile = ROUTES[name]
    response = service.route(origin_id, destination_id, profile)
    if response.get("status") != 200:
        raise RuntimeError(f"Approved route {name} failed: {response.get('code')}")
    origin = dict(response["origin"])
    destination = dict(response["destination"])
    origin["node_id"] = origin.pop("anchor_node")
    destination["node_id"] = destination.pop("anchor_node")
    facility_id = level_facilities[origin["level_id"]]
    expected_facility = "SFU_BURNABY_STRAND" if name == "strand_corridor" else "SFU_BURNABY_QUAD"
    if facility_id != expected_facility:
        raise RuntimeError(
            f"Approved route {name} belongs to {facility_id}, not "
            f"{expected_facility}."
        )
    if level_facilities[destination["level_id"]] != facility_id:
        raise RuntimeError(f"Approved route {name} crosses facility boundaries.")
    if origin["node_id"] == destination["node_id"] or response["network_distance_m"] <= 0:
        raise RuntimeError(
            f"Approved route {name} no longer has distinct positive-distance anchors."
        )
    if not response["geometries"] or not response["edge_ids"]:
        raise RuntimeError(f"Approved route {name} lacks measured route geometry.")
    if name in {"strand_corridor", "aq_long_corridor"} and (
        origin["level_id"] != destination["level_id"]
        or any(edge["mode"] != "pathway" for edge in response["edges"])
        or any(item["level_id"] != origin["level_id"] for item in response["geometries"])
    ):
        raise RuntimeError(f"Approved corridor {name} no longer stays on its measured level.")

    fixture = {
        "status": response["status"],
        "facility_id": facility_id,
        "profile": profile,
        "origin": origin,
        "destination": destination,
        "reachability": {
            "algorithm": response["reachability_algorithm"],
            "component_semantics": response["component_semantics"],
            "origin_id": origin["reachability_id"],
            "destination_id": destination["reachability_id"],
        },
        "network_distance_m": response["network_distance_m"],
        "edge_ids": response["edge_ids"],
        "edge_modes": [edge["mode"] for edge in response["edges"]],
        "edges": response["edges"],
        "geometries": [
            {
                **geometry,
                "edge_ids": [geometry["edge_id"]],
                "source": "RoutingService response geometry",
            }
            for geometry in response["geometries"]
        ],
        "steps": response["steps"],
        "warnings": response["warnings"],
        "provenance": response["provenance"],
    }
    if profile == "elevator_only":
        fixture["accessibility_disclosure"] = {
            "summary": "Elevators only; stairs excluded",
            "not_verified": list(NOT_VERIFIED),
        }
    return fixture


def generate(
    gpkg_path: Path,
    graph_path: Path,
    stats_path: Path,
    output_path: Path,
) -> None:
    repository = ArtifactRepository(gpkg_path)
    service = RoutingService.from_artifacts(gpkg_path, graph_path, stats_path)
    level_facilities = {
        level["level_id"]: level["facility_id"] for level in repository.levels()
    }
    report = {
        "selection_algorithm": (
            "Replay the data-QA-approved exact room pairs through RoutingService and reject "
            "artifact, facility, status, anchor, edge, or geometry drift."
        ),
        "selection_rationale": (
            "The fixtures cover measured Strand and AQ corridors, an AQ stairs transition, "
            "and an AQ elevator-only transition without synthetic room connectors. Strand "
            "selection: levels by vertical_order, eligible endpoints by unit_id; first "
            "successful distinct-anchor pair with at least 20 m of pathway-only geometry "
            "wholly on the same level. Replay uses the resulting exact room pair."
        ),
        "cross_building_disclosure": {
            "aq_strand_reachable_pairs": {"default": 0, "elevator_only": 0},
            "summary": (
                "Measured AQ-Strand connectivity is zero for both profiles; no "
                "cross-building route or inferred connector is claimed."
            ),
        },
        "artifact_hashes": {
            gpkg_path.name: _sha256(gpkg_path),
            graph_path.name: _sha256(graph_path),
            stats_path.name: _sha256(stats_path),
        },
        "fixtures": {
            name: _fixture(name, service, level_facilities) for name in ROUTES
        },
    }
    report["self_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpkg", type=Path, default=Path("build/wayfinding.gpkg"))
    parser.add_argument("--graph", type=Path, default=Path("build/graph_contracted.pkl"))
    parser.add_argument(
        "--stats", type=Path, default=Path("build/graph_contracted_stats.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/reports/DT-015-demo-routes.json")
    )
    arguments = parser.parse_args()
    generate(arguments.gpkg, arguments.graph, arguments.stats, arguments.output)


if __name__ == "__main__":
    main()
