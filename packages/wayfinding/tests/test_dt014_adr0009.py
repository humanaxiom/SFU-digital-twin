"""RED contracts for ADR-0009 judge and data-QA findings."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
import pytest
from shapely.geometry import LineString

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
GPKG_PATH = WORKSPACE_ROOT / "build" / "wayfinding.gpkg"
GRAPH_PATH = WORKSPACE_ROOT / "build" / "graph_contracted.pkl"
STATS_PATH = WORKSPACE_ROOT / "build" / "graph_contracted_stats.json"
EVIDENCE_PATH = WORKSPACE_ROOT / "docs" / "reports" / "DT-014-route-evidence.json"
PROFILE_TOTALS = {"default": 816, "elevator_only": 840}
PROFILE_ISOLATED_TOTALS = {"default": 0, "elevator_only": 3}
ENDPOINT_REACHABILITY_FIELDS = {
    "unit_id",
    "level_id",
    "anchor_node",
    "attachment_distance_m",
    "component_id",
    "reachability_id",
    "reachability_kind",
}


def _routing() -> Any:
    return importlib.import_module("wayfinding.demo.routing")


def _real_service() -> Any:
    return _routing().RoutingService.from_artifacts(GPKG_PATH, GRAPH_PATH, STATS_PATH)


def _provenance() -> dict[str, str]:
    return {
        "gpkg_sha256": "a" * 64,
        "graph_sha256": "b" * 64,
        "stats_sha256": "c" * 64,
        "source_status": "accepted legacy snapshot; final source-directory lineage pending DT-009",
        "algorithm_version": "dt014-v1",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(-0.0, b"0", id="negative-zero-number"),
        pytest.param("\u2028", "\"\u2028\"".encode(), id="unescaped-valid-unicode-string"),
        pytest.param(
            {"\ue000": 2, "\U0001f600": 1},
            '{"\U0001f600":1,"\ue000":2}'.encode(),
            id="utf16-object-key-order",
        ),
    ],
)
def test_canonical_serializer_passes_independent_rfc8785_vectors(
    value: Any,
    expected: bytes,
):
    ordinary = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    assert ordinary != expected, "the vector must distinguish RFC 8785 from ordinary json.dumps"
    assert _routing()._canonical_json(value) == expected


def test_canonical_serializer_delegates_to_a_conforming_rfc8785_library():
    module = _routing()
    serializer = getattr(module, "rfc8785", None) or getattr(module, "_rfc8785", None)

    assert serializer is not None, "canonical JSON must use a conforming RFC 8785 library"
    assert module._canonical_json({"value": -0.0}) == serializer.dumps({"value": -0.0})


def test_node_ordering_uses_canonical_json_bytes_for_nearest_ties():
    canonical_first = ("a",)
    repr_first = ("z'b",)
    assert repr(repr_first) < repr(canonical_first)
    assert _routing()._canonical_json(canonical_first) < _routing()._canonical_json(
        repr_first
    )

    anchors = []
    for insertion_order in (
        (repr_first, canonical_first),
        (canonical_first, repr_first),
    ):
        graph = nx.MultiDiGraph()
        for node in insertion_order:
            graph.add_node(node, x=0.0, y=0.0, level_ids={"L1"})
        service = _routing().RoutingService.from_graph(
            graph,
            [
                {
                    "unit_id": "U",
                    "room_id": "A100",
                    "level_id": "L1",
                    "centroid": (0, 0),
                }
            ],
            _provenance(),
        )
        anchors.append(service.endpoint_catalog["U"]["anchor_node"])

    assert anchors == [canonical_first, canonical_first]


def test_equal_cost_route_tie_uses_canonical_json_bytes():
    origin = ("origin",)
    canonical_middle = ("a",)
    repr_middle = ("z'b",)
    destination = ("destination",)
    graph = nx.MultiDiGraph()
    coordinates = {
        origin: (0.0, 0.0),
        canonical_middle: (1.0, 1.0),
        repr_middle: (1.0, -1.0),
        destination: (2.0, 0.0),
    }
    for node, (x, y) in coordinates.items():
        graph.add_node(node, x=x, y=y, level_ids={"L1"})
    for source, target, key in (
        (origin, repr_middle, "repr-1"),
        (repr_middle, destination, "repr-2"),
        (origin, canonical_middle, "canonical-1"),
        (canonical_middle, destination, "canonical-2"),
    ):
        graph.add_edge(
            source,
            target,
            key=key,
            mode="pathway",
            length_3d=1.0,
            level_id="L1",
            feature_id=key,
            original_feature_ids=[key],
            geometry=LineString([coordinates[source], coordinates[target]]),
        )
    service = _routing().RoutingService.from_graph(
        graph,
        [
            {"unit_id": "U-A", "room_id": "A", "level_id": "L1", "centroid": (0, 0)},
            {"unit_id": "U-B", "room_id": "B", "level_id": "L1", "centroid": (2, 0)},
        ],
        _provenance(),
    )

    response = service.route("U-A", "U-B", "default")

    assert response["status"] == 200
    assert response["node_ids"] == [origin, canonical_middle, destination]


def test_evidence_document_has_complete_adr0009_audit_fields():
    service = _real_service()
    evidence = service.evidence_document()

    assert evidence["component_counts"] == PROFILE_TOTALS
    assert evidence["profile_isolated_counts"] == PROFILE_ISOLATED_TOTALS
    assert evidence["profile_isolated_counts"] == {
        profile: service.profile_isolated_count(profile)
        for profile in PROFILE_TOTALS
    }
    for name, pair in evidence["pairs"].items():
        assert {
            "precheck_result",
            "shortest_path_invoked",
            "edge_count",
            "http_status",
        } <= set(pair), name
        assert ENDPOINT_REACHABILITY_FIELDS <= set(pair["origin"]), name
        assert ENDPOINT_REACHABILITY_FIELDS <= set(pair["destination"]), name


@pytest.mark.dataqa
def test_checked_in_evidence_is_canonical_self_hashed_and_complete():
    raw = EVIDENCE_PATH.read_bytes()
    assert not raw.endswith(b"\n")
    evidence = json.loads(raw)
    published_hash = evidence.pop("evidence_sha256")
    canonical_without_self_hash = _routing()._canonical_json(evidence)

    assert raw == _routing()._canonical_json({**evidence, "evidence_sha256": published_hash})
    assert published_hash == hashlib.sha256(canonical_without_self_hash).hexdigest()
    assert evidence["component_counts"] == PROFILE_TOTALS
    assert evidence["profile_isolated_counts"] == PROFILE_ISOLATED_TOTALS


@pytest.mark.dataqa
def test_checked_in_evidence_pairs_have_complete_reachability_and_audit_fields():
    evidence = json.loads(EVIDENCE_PATH.read_bytes())

    for name, pair in evidence["pairs"].items():
        assert {
            "precheck_result",
            "shortest_path_invoked",
            "edge_count",
            "network_distance_m",
            "http_status",
        } <= set(pair), name
        assert ENDPOINT_REACHABILITY_FIELDS <= set(pair["origin"]), name
        assert ENDPOINT_REACHABILITY_FIELDS <= set(pair["destination"]), name


@pytest.mark.dataqa
def test_accepted_artifact_evidence_includes_profile_isolated_same_anchor_when_available():
    service = _real_service()
    units_by_isolated_anchor: dict[Any, list[str]] = defaultdict(list)
    for unit_id, endpoint in service.endpoint_catalog.items():
        if (
            endpoint["eligible"]
            and endpoint["reachability_kinds"]["elevator_only"]
            == "profile_isolated_singleton"
        ):
            units_by_isolated_anchor[endpoint["anchor_node"]].append(unit_id)
    candidates = sorted(
        (unit_ids[0], unit_ids[1])
        for unit_ids in (sorted(values) for values in units_by_isolated_anchor.values())
        if len(unit_ids) >= 2
    )
    if not candidates:
        pytest.skip("accepted artifact has no eligible profile-isolated same-anchor unit pair")

    pair = service.evidence_document()["pairs"]["elevator_only_profile_isolated_same_anchor"]
    assert (pair["origin_unit_id"], pair["destination_unit_id"]) == candidates[0]
    assert pair["http_status"] == 200
    assert pair["precheck_result"] == "same_reachability"
    assert pair["shortest_path_invoked"] is False
    assert pair["edge_count"] == 0
    assert pair["network_distance_m"] == 0
    assert pair["origin"]["reachability_kind"] == "profile_isolated_singleton"
    assert pair["origin"]["anchor_node"] == pair["destination"]["anchor_node"]


def test_dt014_non_traversal_anchors_are_bounded_poc_exception_without_connectors():
    """ADR-0008 anchors are a bounded PoC exception to future zero-cost unit connectors."""
    anchor = (0.0, 0.0, 0)
    stairs_peer = (2.0, 0.0, 0)
    graph = nx.MultiDiGraph()
    for node in (anchor, stairs_peer):
        graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
    graph.add_edge(
        anchor,
        stairs_peer,
        key="S1",
        mode="stairs",
        length_3d=2.0,
        level_id="L1",
        feature_id="S1",
        original_feature_ids=["S1"],
        geometry=LineString([(0, 0), (2, 0)]),
    )
    edges_before = list(graph.edges(keys=True, data=True))
    service = _routing().RoutingService.from_graph(
        graph,
        [
            {"unit_id": "U-A", "room_id": "A", "level_id": "L1", "centroid": (0, 0)},
            {"unit_id": "U-B", "room_id": "B", "level_id": "L1", "centroid": (0.1, 0)},
        ],
        _provenance(),
    )

    response = service.route("U-A", "U-B", "elevator_only")

    assert list(graph.edges(keys=True, data=True)) == edges_before
    assert not any(str(key).startswith("UC_") for _u, _v, key in graph.edges(keys=True))
    assert response["status"] == 200
    assert response["edge_ids"] == []
    assert response["edges"] == []
    assert response["geometries"] == []
    assert response["network_distance_m"] == 0
    assert "room-to-anchor traversal is not represented or verified" in response["warnings"]
