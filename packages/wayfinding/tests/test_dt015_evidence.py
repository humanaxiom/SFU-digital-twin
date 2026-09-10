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


def _load_evidence() -> dict[str, Any]:
    assert EVIDENCE_PATH.is_file(), "Data QA must check in docs/reports/DT-015-demo-routes.json"
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _fixtures(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fixtures = evidence.get("fixtures")
    assert isinstance(fixtures, dict)
    assert set(fixtures) == {"strand_corridor", "aq_corridor", "aq_transition"}
    return fixtures


def test_dt015_three_demo_routes_are_real_deterministic_and_replayable():
    evidence = _load_evidence()
    fixtures = _fixtures(evidence)

    assert evidence["selection_algorithm"]
    assert evidence["selection_rationale"]
    assert evidence["artifact_hashes"] == {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in ARTIFACT_PATHS.items()
    }
    assert fixtures["strand_corridor"]["facility_id"] == "SFU_BURNABY_STRAND"
    assert fixtures["aq_corridor"]["facility_id"] == "SFU_BURNABY_QUAD"
    assert fixtures["aq_transition"]["facility_id"] == "SFU_BURNABY_QUAD"
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
        fixtures["strand_corridor"]["origin"]["level_id"]
        == fixtures["strand_corridor"]["destination"]["level_id"]
    )
    assert (
        fixtures["aq_corridor"]["origin"]["level_id"]
        == fixtures["aq_corridor"]["destination"]["level_id"]
    )
    assert (
        fixtures["aq_transition"]["origin"]["level_id"]
        != fixtures["aq_transition"]["destination"]["level_id"]
    )
    assert {"stairs", "elevator"} & set(fixtures["aq_transition"]["edge_modes"])
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
