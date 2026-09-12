"""RED deterministic demonstration-evidence contracts for DT-015."""

import hashlib
import json
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
EVIDENCE_PATH = WORKSPACE_ROOT / "docs/reports/DT-015-demo-routes.json"
ARTIFACT_PATHS = {
    "wayfinding.gpkg": WORKSPACE_ROOT / "build/wayfinding.gpkg",
    "graph_contracted.pkl": WORKSPACE_ROOT / "build/graph_contracted.pkl",
    "graph_contracted_stats.json": WORKSPACE_ROOT / "build/graph_contracted_stats.json",
}
UNVERIFIED = {"door_width", "path_width", "slope", "powered_doors", "surface"}


def test_dt015_generator_reproduces_checked_in_evidence(tmp_path):
    """The saved report must remain reproducible from the accepted artifacts."""
    from wayfinding.demo.evidence import generate

    output = tmp_path / "regenerated.json"
    generate(
        ARTIFACT_PATHS["wayfinding.gpkg"],
        ARTIFACT_PATHS["graph_contracted.pkl"],
        ARTIFACT_PATHS["graph_contracted_stats.json"],
        output,
    )
    assert json.loads(output.read_text(encoding="utf-8")) == _load_evidence()


def _load_evidence() -> dict[str, Any]:
    assert EVIDENCE_PATH.is_file(), "Data QA must check in docs/reports/DT-015-demo-routes.json"
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _fixtures(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fixtures = evidence.get("fixtures")
    assert isinstance(fixtures, dict)
    assert set(fixtures) == {"aq_long_corridor", "aq_stairs", "aq_elevator", "strand_corridor"}
    return fixtures


def test_dt015_demo_routes_are_real_deterministic_and_replayable():
    evidence = _load_evidence()
    fixtures = _fixtures(evidence)

    assert evidence["selection_algorithm"]
    assert evidence["selection_rationale"]
    assert evidence["artifact_hashes"] == {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in ARTIFACT_PATHS.items()
    }
    for name, fixture in fixtures.items():
        expected = "SFU_BURNABY_STRAND" if name == "strand_corridor" else "SFU_BURNABY_QUAD"
        assert fixture["facility_id"] == expected
    assert evidence["cross_building_disclosure"]["aq_strand_reachable_pairs"] == {
        "default": 0,
        "elevator_only": 0,
    }
    for name, fixture in fixtures.items():
        assert fixture["status"] == 200, name
        assert fixture["origin"]["unit_id"] != fixture["destination"]["unit_id"], name
        assert fixture["origin"]["node_id"] != fixture["destination"]["node_id"], name
        assert fixture["network_distance_m"] > 0, name
        assert fixture["edge_ids"], name
        assert fixture["edge_modes"], name
        assert fixture["geometries"], name
        assert fixture["steps"], name
        assert fixture["reachability"], name
        assert fixture["provenance"], name
    assert (
        fixtures["aq_long_corridor"]["origin"]["level_id"]
        == fixtures["aq_long_corridor"]["destination"]["level_id"]
    )
    strand = fixtures["strand_corridor"]
    assert strand["origin"]["level_id"] == strand["destination"]["level_id"]
    assert strand["profile"] == "default"
    assert set(strand["edge_modes"]) == {"pathway"}
    assert {item["level_id"] for item in strand["geometries"]} == {
        strand["origin"]["level_id"]
    }
    assert strand["network_distance_m"] >= 20
    assert (
        fixtures["aq_stairs"]["origin"]["level_id"]
        != fixtures["aq_stairs"]["destination"]["level_id"]
    )
    assert (
        fixtures["aq_elevator"]["origin"]["level_id"]
        != fixtures["aq_elevator"]["destination"]["level_id"]
    )
    assert "stairs" in fixtures["aq_stairs"]["edge_modes"]
    assert fixtures["aq_elevator"]["profile"] == "elevator_only"
    assert "elevator" in fixtures["aq_elevator"]["edge_modes"]
    assert "stairs" not in fixtures["aq_elevator"]["edge_modes"]
    canonical = json.dumps(
        {key: value for key, value in evidence.items() if key != "self_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    assert evidence["self_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_dt015_routes_use_only_recorded_edges_and_no_connector_geometry():
    evidence = _load_evidence()

    for name, fixture in _fixtures(evidence).items():
        assert len(fixture["edge_ids"]) == len(fixture["edge_modes"]), name
        assert set(fixture["edge_modes"]) <= {"pathway", "stairs", "elevator"}, name
        assert "connector" not in {mode.lower() for mode in fixture["edge_modes"]}, name
        assert all(geometry["edge_ids"] for geometry in fixture["geometries"]), name
        returned_geometry_edges = {
            edge_id
            for geometry in fixture["geometries"]
            for edge_id in geometry["edge_ids"]
        }
        assert returned_geometry_edges <= set(fixture["edge_ids"]), name
        assert all(
            "room" not in geometry.get("source", "").lower()
            for geometry in fixture["geometries"]
        ), name
        if fixture["profile"] == "elevator_only":
            assert "stairs" not in fixture["edge_modes"], name
            disclosure = fixture["accessibility_disclosure"]
            assert disclosure["summary"] == "Elevators only; stairs excluded"
            assert set(disclosure["not_verified"]) == UNVERIFIED
