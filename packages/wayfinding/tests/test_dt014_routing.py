"""RED contracts for the ADR-0008 bounded indoor routing proof of concept."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
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
NOT_VERIFIED = ["door_width", "path_width", "slope", "powered_doors", "surface"]
ALLOWED_MODES = {
    "default": ["elevator", "pathway", "stairs"],
    "elevator_only": ["elevator", "pathway"],
}
SOURCE_STATUS = "accepted legacy snapshot; final source-directory lineage pending DT-009"
REACHABILITY_ALGORITHM = "profile-reachability-rfc8785-sha256-v1"


def _routing_module() -> Any:
    try:
        module = importlib.import_module("wayfinding.demo.routing")
    except ImportError as error:
        pytest.fail(f"DT-014 routing module is not implemented: {error}")
    assert hasattr(module, "RoutingService"), "routing must define RoutingService"
    assert hasattr(module, "RouteArtifactError"), "routing must define RouteArtifactError"
    return module


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return _routing_module()._canonical_json(value)


def _expected_component_id(profile: str, nodes: set[Any]) -> str:
    sorted_nodes = sorted(nodes, key=_canonical_json)
    payload = {"kind": "counted_component", "nodes": sorted_nodes, "profile": profile}
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _expected_isolated_reachability_id(profile: str, node: Any) -> str:
    payload = {
        "kind": "profile_isolated_singleton",
        "node": node,
        "profile": profile,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _provenance() -> dict[str, str]:
    return {
        "gpkg_sha256": "a" * 64,
        "graph_sha256": "b" * 64,
        "stats_sha256": "c" * 64,
        "source_status": SOURCE_STATUS,
        "algorithm_version": "dt014-v1",
    }


def _edge(
    graph: nx.MultiDiGraph,
    source: tuple[float, float, int],
    target: tuple[float, float, int],
    key: str,
    *,
    mode: str = "pathway",
    length: float = 1.0,
    level_id: str = "L1",
) -> None:
    graph.add_edge(
        source,
        target,
        key=key,
        mode=mode,
        length_3d=length,
        level_id=level_id,
        feature_id=key,
        original_feature_ids=[key],
        geometry=LineString([(source[0], source[1]), (target[0], target[1])]),
    )


def _unit(unit_id: str, room_id: str, level_id: str, x: float, y: float) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "room_id": room_id,
        "level_id": level_id,
        "centroid": (x, y),
    }


def _base_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node, level_ids in (
        ((0.0, 0.0, 0), {"L1"}),
        ((2.0, 0.0, 0), {"L1"}),
        ((4.0, 0.0, 0), {"L1"}),
        ((2.0, 2.0, 1), {"L2"}),
    ):
        graph.add_node(node, x=node[0], y=node[1], level_ids=level_ids)
    _edge(graph, (0.0, 0.0, 0), (2.0, 0.0, 0), "P1", length=2.0)
    _edge(graph, (2.0, 0.0, 0), (4.0, 0.0, 0), "P2", length=2.0)
    _edge(
        graph,
        (2.0, 0.0, 0),
        (2.0, 2.0, 1),
        "E1",
        mode="elevator",
        length=3.0,
        level_id="L1",
    )
    return graph


def _service(
    graph: nx.MultiDiGraph | None = None,
    units: list[dict[str, Any]] | None = None,
) -> Any:
    graph = graph or _base_graph()
    units = units or [
        _unit("U-A", "A100", "L1", 0.5, 0.0),
        _unit("U-B", "A102", "L1", 3.5, 0.0),
        _unit("U-C", "A200", "L2", 2.0, 2.0),
    ]
    return _routing_module().RoutingService.from_graph(graph, units, _provenance())


def _real_service() -> Any:
    for path in (GPKG_PATH, GRAPH_PATH, STATS_PATH):
        assert path.is_file(), f"Approved DT-014 artifact is missing: {path.name}"
    return _routing_module().RoutingService.from_artifacts(GPKG_PATH, GRAPH_PATH, STATS_PATH)


def _assert_provenance(payload: dict[str, Any]) -> None:
    provenance = payload["provenance"]
    assert set(provenance) == {
        "gpkg_sha256",
        "graph_sha256",
        "stats_sha256",
        "source_status",
        "algorithm_version",
    }
    assert all(len(provenance[name]) == 64 for name in provenance if name.endswith("sha256"))
    assert provenance["source_status"] == SOURCE_STATUS


def _assert_elevator_disclosure(payload: dict[str, Any]) -> None:
    assert payload["profile"] == "elevator_only"
    assert payload["accessibility"] == {
        "basis": "TRANSITION_TYPE=4 (elevator) only; stairs excluded",
        "not_verified": NOT_VERIFIED,
    }
    rendered = json.dumps(payload).lower()
    assert "wheelchair-certified" not in rendered
    assert "guaranteed step-free" not in rendered


def _assert_endpoint_reachability(endpoint: dict[str, Any], *, isolated: bool) -> None:
    assert {
        "unit_id",
        "level_id",
        "anchor_node",
        "attachment_distance_m",
        "component_id",
        "reachability_id",
        "reachability_kind",
    } <= set(endpoint)
    assert re.fullmatch(r"[0-9a-f]{64}", endpoint["reachability_id"])
    if isolated:
        assert endpoint["component_id"] is None
        assert endpoint["reachability_kind"] == "profile_isolated_singleton"
    else:
        assert endpoint["component_id"] == endpoint["reachability_id"]
        assert endpoint["reachability_kind"] == "counted_component"


def _assert_reachability_envelope(payload: dict[str, Any], profile: str) -> None:
    assert payload["component_semantics"] == "edge_induced"
    assert payload["component_count"] >= 0
    assert payload["reachability_algorithm"] == REACHABILITY_ALGORITHM
    assert payload["profile"] == profile


def test_startup_uses_exact_real_artifact_hashes_and_keeps_graph_unchanged():
    graph_before = GRAPH_PATH.read_bytes()
    gpkg_before = _hash(GPKG_PATH)

    service = _real_service()

    assert service.provenance == {
        "gpkg_sha256": gpkg_before,
        "graph_sha256": hashlib.sha256(graph_before).hexdigest(),
        "stats_sha256": _hash(STATS_PATH),
        "source_status": SOURCE_STATUS,
        "algorithm_version": service.provenance["algorithm_version"],
    }
    assert GRAPH_PATH.read_bytes() == graph_before
    assert _hash(GPKG_PATH) == gpkg_before


def test_real_artifact_catalog_and_profile_components_match_measured_sidecar():
    service = _real_service()
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))

    assert len(service.endpoint_catalog) == 1017
    assert service.component_count("default") == stats["component_counts"]["default"] == 816
    assert service.component_count("elevator_only") == (
        stats["component_counts"]["elevator_only"]
    ) == 840
    for profile in ALLOWED_MODES:
        identifiers = set(service.component_ids[profile].values())
        assert len(identifiers) == service.component_count(profile)
        assert all(re.fullmatch(r"[0-9a-f]{64}", identifier) for identifier in identifiers)

    elevator_only_isolated = set(service.graph.nodes) - set(
        service.component_ids["elevator_only"]
    )
    assert len(elevator_only_isolated) == 3

    for endpoint in service.endpoint_catalog.values():
        for profile in ALLOWED_MODES:
            reachability_id = endpoint["reachability_ids"][profile]
            reachability_kind = endpoint["reachability_kinds"][profile]
            assert re.fullmatch(r"[0-9a-f]{64}", reachability_id)
            if endpoint["component_ids"][profile] is None:
                assert reachability_kind == "profile_isolated_singleton"
            else:
                assert reachability_kind == "counted_component"
                assert reachability_id == endpoint["component_ids"][profile]


@pytest.mark.parametrize("missing_name", ["wayfinding.gpkg", "graph_contracted.pkl", "stats.json"])
def test_startup_fails_closed_when_any_artifact_is_missing(tmp_path: Path, missing_name: str):
    paths = {
        "wayfinding.gpkg": GPKG_PATH,
        "graph_contracted.pkl": GRAPH_PATH,
        "stats.json": STATS_PATH,
    }
    arguments = []
    for name, source in paths.items():
        target = tmp_path / name
        if name != missing_name:
            target.write_bytes(source.read_bytes())
        arguments.append(target)

    with pytest.raises(_routing_module().RouteArtifactError) as caught:
        _routing_module().RoutingService.from_artifacts(*arguments)

    assert caught.value.code == "artifact_mismatch"
    assert caught.value.status == 503


@pytest.mark.parametrize("artifact", ["gpkg", "graph"])
def test_startup_fails_closed_on_lineage_hash_mismatch(tmp_path: Path, artifact: str):
    gpkg = tmp_path / "wayfinding.gpkg"
    graph = tmp_path / "graph.pkl"
    stats = tmp_path / "stats.json"
    gpkg.write_bytes(GPKG_PATH.read_bytes())
    graph.write_bytes(GRAPH_PATH.read_bytes())
    stats.write_bytes(STATS_PATH.read_bytes())
    (gpkg if artifact == "gpkg" else graph).write_bytes(b"tampered")

    with pytest.raises(_routing_module().RouteArtifactError) as caught:
        _routing_module().RoutingService.from_artifacts(gpkg, graph, stats)

    assert caught.value.code == "artifact_mismatch"
    assert caught.value.status == 503


def test_startup_fails_closed_on_graph_deserialization_error(tmp_path: Path):
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    corrupt_graph = tmp_path / "graph.pkl"
    corrupt_graph.write_bytes(b"not a pickle")
    for item in stats["lineage"]["outputs"]:
        if item["path"].endswith("graph_contracted.pkl"):
            item["sha256"] = _hash(corrupt_graph)
    stats_path = tmp_path / "stats.json"
    stats_path.write_text(json.dumps(stats), encoding="utf-8")

    with pytest.raises(_routing_module().RouteArtifactError) as caught:
        _routing_module().RoutingService.from_artifacts(
            GPKG_PATH,
            corrupt_graph,
            stats_path,
        )

    assert caught.value.code == "artifact_mismatch"
    assert caught.value.status == 503


def test_endpoint_catalog_selects_exact_same_level_nearest_node_without_mutation():
    graph = _base_graph()
    nodes_before = list(graph.nodes(data=True))
    edges_before = list(graph.edges(keys=True, data=True))

    service = _service(graph, [_unit("U", "A100", "L1", 1.6, 0.0)])
    endpoint = service.endpoint_catalog["U"]

    assert endpoint["anchor_node"] == (2.0, 0.0, 0)
    assert endpoint["level_id"] == "L1"
    assert endpoint["attachment_distance_m"] == pytest.approx(0.4)
    assert endpoint["attachment_crs"] == "EPSG:26910"
    assert endpoint["approximate"] is True
    assert "geometry" not in endpoint
    assert list(graph.nodes(data=True)) == nodes_before
    assert list(graph.edges(keys=True, data=True)) == edges_before
    assert not any(str(key).startswith("UC_") for _u, _v, key in graph.edges(keys=True))


def test_endpoint_catalog_uses_lexicographic_ties_and_is_insertion_order_independent():
    left = (0.0, 0.0, 0)
    right = (2.0, 0.0, 0)
    units = [_unit("U", "A100", "L1", 1.0, 0.0)]
    anchors = []
    for insertion_order in ((right, left), (left, right)):
        graph = nx.MultiDiGraph()
        for node in insertion_order:
            graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
        anchors.append(_service(graph, units).endpoint_catalog["U"]["anchor_node"])

    assert anchors == [left, left]


def test_endpoint_catalog_records_are_deeply_immutable():
    endpoint = _service().endpoint_catalog["U-A"]

    with pytest.raises(TypeError):
        endpoint["eligible"] = False
    with pytest.raises(TypeError):
        endpoint["component_ids"]["default"] = "forged"
    with pytest.raises(TypeError):
        endpoint["reachability_ids"]["default"] = "forged"
    with pytest.raises(TypeError):
        endpoint["reachability_kinds"]["default"] = "forged"


@pytest.mark.parametrize(
    ("unit", "reason", "distance"),
    [
        (_unit("U", "A100", "L1", 10.01, 0.0), "attachment_over_limit", 10.01),
        (_unit("U", "A100", "L9", 0.0, 0.0), "no_same_level_node", None),
        ({"unit_id": "U", "room_id": "A100", "level_id": "L1", "centroid": None},
         "missing_centroid", None),
    ],
)
def test_endpoint_catalog_records_bounded_unavailable_reasons(
    unit: dict[str, Any],
    reason: str,
    distance: float | None,
):
    graph = nx.MultiDiGraph()
    graph.add_node((0.0, 0.0, 0), x=0.0, y=0.0, level_ids={"L1"})

    endpoint = _service(graph, [unit]).endpoint_catalog["U"]

    assert endpoint["eligible"] is False
    assert endpoint["unavailable_reason"] == reason
    assert endpoint["attachment_distance_m"] == distance


def test_exact_resolution_reports_unknown_ambiguous_and_bounded_identifiers():
    service = _service(
        units=[
            _unit("U-1", "DUP", "L1", 0.0, 0.0),
            _unit("U-2", "DUP", "L1", 2.0, 0.0),
        ]
    )

    assert service.resolve_endpoint("U-1")["unit_id"] == "U-1"
    assert service.resolve_endpoint("missing") == {"status": 404, "code": "unknown_endpoint"}
    assert service.resolve_endpoint("DUP")["status"] == 409
    assert service.resolve_endpoint("DUP")["code"] == "ambiguous_endpoint"
    assert service.resolve_endpoint("x" * 256)["status"] == 400


def test_profile_component_and_reachability_ids_are_stable_across_insertion_order():
    graph = _base_graph()
    _edge(
        graph,
        (4.0, 0.0, 0),
        (2.0, 2.0, 1),
        "S1",
        mode="stairs",
        length=1.0,
    )
    reversed_graph = nx.MultiDiGraph()
    reversed_graph.add_nodes_from(reversed(list(graph.nodes(data=True))))
    reversed_graph.add_edges_from(reversed(list(graph.edges(keys=True, data=True))))

    first = _service(graph)
    second = _service(reversed_graph)

    assert first.allowed_modes == ALLOWED_MODES
    assert first.component_ids == second.component_ids
    assert {
        unit_id: dict(endpoint["reachability_ids"])
        for unit_id, endpoint in first.endpoint_catalog.items()
    } == {
        unit_id: dict(endpoint["reachability_ids"])
        for unit_id, endpoint in second.endpoint_catalog.items()
    }
    assert first.component_ids["default"][(4.0, 0.0, 0)] == first.component_ids["default"][
        (2.0, 2.0, 1)
    ]
    assert set(first.component_ids["default"].values()) == {
        _expected_component_id("default", set(graph.nodes))
    }
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", identifier)
        for profile_ids in first.component_ids.values()
        for identifier in profile_ids.values()
    )


def test_distinct_stairs_only_anchors_are_profile_isolated_and_fail_before_search(
    monkeypatch: pytest.MonkeyPatch,
):
    origin = (0.0, 0.0, 0)
    destination = (2.0, 0.0, 0)
    graph = nx.MultiDiGraph()
    for node in (origin, destination):
        graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
    _edge(graph, origin, destination, "S1", mode="stairs", length=2.0)
    service = _service(
        graph,
        [_unit("U-A", "A", "L1", 0.0, 0.0), _unit("U-B", "B", "L1", 2.0, 0.0)],
    )
    reversed_graph = nx.MultiDiGraph()
    reversed_graph.add_nodes_from(reversed(list(graph.nodes(data=True))))
    reversed_graph.add_edges_from(graph.edges(keys=True, data=True))
    reversed_service = _service(
        reversed_graph,
        [_unit("U-A", "A", "L1", 0.0, 0.0), _unit("U-B", "B", "L1", 2.0, 0.0)],
    )

    def unexpected_search(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("reachability mismatch must return before shortest-path search")

    assert service.route("U-A", "U-B", "default")["status"] == 200

    monkeypatch.setattr(service, "_shortest_path", unexpected_search)
    response = service.route("U-A", "U-B", "elevator_only")

    assert response["status"] == 409
    assert response["code"] == "no_elevator_only_route"
    assert response["search_executed"] is False
    assert service.component_count("elevator_only") == 0
    assert set(service.component_ids["elevator_only"]) == set()
    assert service.component_ids["elevator_only"] == reversed_service.component_ids[
        "elevator_only"
    ]
    _assert_reachability_envelope(response, "elevator_only")
    _assert_endpoint_reachability(response["origin"], isolated=True)
    _assert_endpoint_reachability(response["destination"], isolated=True)
    assert response["origin"]["reachability_id"] != response["destination"][
        "reachability_id"
    ]
    assert response["origin"]["reachability_id"] == _expected_isolated_reachability_id(
        "elevator_only", origin
    )
    assert response["destination"]["reachability_id"] == (
        _expected_isolated_reachability_id("elevator_only", destination)
    )
    assert response["origin"]["reachability_id"] == reversed_service.route(
        "U-A", "U-B", "elevator_only"
    )["origin"]["reachability_id"]


def test_profile_isolated_anchor_to_counted_component_fails_before_search(
    monkeypatch: pytest.MonkeyPatch,
):
    isolated = (0.0, 0.0, 0)
    connected_a = (2.0, 0.0, 0)
    connected_b = (4.0, 0.0, 0)
    graph = nx.MultiDiGraph()
    for node in (isolated, connected_a, connected_b):
        graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
    _edge(graph, isolated, connected_a, "S1", mode="stairs", length=2.0)
    _edge(graph, connected_a, connected_b, "P1", length=2.0)
    service = _service(
        graph,
        [_unit("U-I", "I", "L1", 0.0, 0.0), _unit("U-C", "C", "L1", 4.0, 0.0)],
    )

    def unexpected_search(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("reachability mismatch must return before shortest-path search")

    monkeypatch.setattr(service, "_shortest_path", unexpected_search)

    response = service.route("U-I", "U-C", "elevator_only")

    assert response["status"] == 409
    assert response["code"] == "no_elevator_only_route"
    assert response["search_executed"] is False
    _assert_reachability_envelope(response, "elevator_only")
    _assert_endpoint_reachability(response["origin"], isolated=True)
    _assert_endpoint_reachability(response["destination"], isolated=False)


def test_two_units_sharing_one_profile_isolated_anchor_return_zero_edge_success(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = (0.0, 0.0, 0)
    stairs_peer = (2.0, 0.0, 0)
    graph = nx.MultiDiGraph()
    for node in (anchor, stairs_peer):
        graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
    _edge(graph, anchor, stairs_peer, "S1", mode="stairs", length=2.0)
    service = _service(
        graph,
        [_unit("U-A", "A", "L1", 0.0, 0.0), _unit("U-B", "B", "L1", 0.1, 0.0)],
    )

    def unexpected_search(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("same isolated anchor must not invoke shortest-path search")

    monkeypatch.setattr(service, "_shortest_path", unexpected_search)

    first = service.route("U-A", "U-B", "elevator_only")
    second = service.route("U-A", "U-B", "elevator_only")

    assert first == second
    assert first["status"] == 200
    assert first["search_executed"] is False
    assert first["edge_ids"] == []
    assert first["network_distance_m"] == 0
    _assert_reachability_envelope(first, "elevator_only")
    _assert_endpoint_reachability(first["origin"], isolated=True)
    _assert_endpoint_reachability(first["destination"], isolated=True)
    assert first["origin"]["anchor_node"] == first["destination"]["anchor_node"]
    assert first["origin"]["reachability_id"] == first["destination"]["reachability_id"]


def test_component_mismatch_returns_before_search_and_never_bridges_gap(
    monkeypatch: pytest.MonkeyPatch,
):
    graph = nx.MultiDiGraph()
    graph.add_node((0.0, 0.0, 0), x=0.0, y=0.0, level_ids={"L1"})
    graph.add_node((20.0, 0.0, 0), x=20.0, y=0.0, level_ids={"L1"})
    service = _service(
        graph,
        [
            _unit("U-A", "A", "L1", 0.0, 0.0),
            _unit("U-B", "B", "L1", 20.0, 0.0),
        ],
    )

    def unexpected_search(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("reachability mismatch must return before shortest-path search")

    monkeypatch.setattr(service, "_shortest_path", unexpected_search)

    response = service.route("U-A", "U-B", "default")

    assert response["status"] == 409
    assert response["code"] == "disconnected"
    assert response["search_executed"] is False
    assert response["origin"]["reachability_id"] != response["destination"][
        "reachability_id"
    ]
    assert graph.number_of_edges() == 0


def test_shortest_path_is_deterministic_and_distance_excludes_attachments():
    graph = nx.MultiDiGraph()
    nodes = [(0.0, 0.0, 0), (1.0, -1.0, 0), (1.0, 1.0, 0), (2.0, 0.0, 0)]
    for node in reversed(nodes):
        graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
    _edge(graph, nodes[0], nodes[2], "P-Z1", length=1.0)
    _edge(graph, nodes[2], nodes[3], "P-Z2", length=1.0)
    _edge(graph, nodes[0], nodes[1], "P-A1", length=1.0)
    _edge(graph, nodes[1], nodes[3], "P-A2", length=1.0)
    service = _service(
        graph,
        [
            _unit("U-A", "A", "L1", 0.5, 0.0),
            _unit("U-B", "B", "L1", 2.5, 0.0),
        ],
    )

    first = service.route("U-A", "U-B", "default")
    second = service.route("U-A", "U-B", "default")

    assert first == second
    assert first["status"] == 200
    assert first["node_ids"] == [nodes[0], nodes[1], nodes[3]]
    assert first["network_distance_m"] == pytest.approx(2.0)
    assert first["origin"]["attachment_distance_m"] == pytest.approx(0.5)
    assert first["destination"]["attachment_distance_m"] == pytest.approx(0.5)
    assert "travel_time" not in first


@pytest.mark.parametrize(
    "invalid_length",
    [None, float("nan"), float("inf"), float("-inf"), 0.0, -1.0],
    ids=["missing", "nan", "positive-infinity", "negative-infinity", "zero", "negative"],
)
def test_selected_edge_with_invalid_length_fails_closed(invalid_length: float | None):
    graph = _base_graph()
    edge = graph.edges[(0.0, 0.0, 0), (2.0, 0.0, 0), "P1"]
    if invalid_length is None:
        edge.pop("length_3d")
    else:
        edge["length_3d"] = invalid_length

    response = _service(graph).route("U-A", "U-B", "default")

    assert response["status"] == 503
    assert response["code"] == "route_validation_failed"
    assert "network_distance_m" not in response


def test_same_room_route_is_a_zero_length_graph_route():
    response = _service().route("U-A", "U-A", "default")

    assert response["status"] == 200
    assert response["network_distance_m"] == 0
    assert response["edge_ids"] == []
    assert [step["type"] for step in response["steps"]] == ["depart", "arrive"]


def test_route_returns_edge_ids_per_level_geometry_steps_and_complete_provenance():
    response = _service().route("U-A", "U-C", "default")

    assert response["status"] == 200
    assert response["crs"] == "EPSG:26910"
    assert response["edge_ids"] == ["P1", "E1"]
    assert response["network_distance_m"] == pytest.approx(5.0)
    assert response["geometries"]
    assert all(item["geometry"]["type"] == "LineString" for item in response["geometries"])
    assert all(item["level_id"] in {"L1", "L2"} for item in response["geometries"])
    assert {step["type"] for step in response["steps"]} <= {
        "depart", "continue", "turn", "enter_transition", "exit_transition", "arrive"
    }
    assert "enter_transition" in [step["type"] for step in response["steps"]]
    rendered_steps = json.dumps(response["steps"]).lower()
    assert "door" not in rendered_steps
    assert "centroid connector" not in rendered_steps
    _assert_reachability_envelope(response, "default")
    _assert_endpoint_reachability(response["origin"], isolated=False)
    _assert_endpoint_reachability(response["destination"], isolated=False)
    _assert_provenance(response)


@pytest.mark.parametrize(
    ("delta_degrees", "expected_type", "expected_verb"),
    [
        (10.0, "continue", "continue"),
        (30.0, "turn", "bear"),
        (90.0, "turn", "turn"),
        (150.0, "turn", "u-turn"),
    ],
)
def test_pathway_instructions_follow_documented_bearing_thresholds(
    delta_degrees: float,
    expected_type: str,
    expected_verb: str,
):
    origin = (0.0, 0.0, 0)
    vertex = (5.0, 0.0, 0)
    radians = math.radians(delta_degrees)
    destination = (5.0 + 5.0 * math.cos(radians), 5.0 * math.sin(radians), 0)
    graph = nx.MultiDiGraph()
    for node in (origin, vertex, destination):
        graph.add_node(node, x=node[0], y=node[1], level_ids={"L1"})
    _edge(graph, origin, vertex, "P1", length=5.0)
    _edge(graph, vertex, destination, "P2", length=5.0)
    service = _service(
        graph,
        [
            _unit("U-A", "A", "L1", origin[0], origin[1]),
            _unit("U-B", "B", "L1", destination[0], destination[1]),
        ],
    )

    response = service.route("U-A", "U-B", "default")
    pathway_steps = [step for step in response["steps"] if "edge_id" in step]

    assert response["status"] == 200
    assert pathway_steps[1]["type"] == expected_type
    assert expected_verb in pathway_steps[1]["instruction"].lower()


def _multi_transition_service() -> Any:
    nodes = (
        ((0.0, 0.0, 0), "L1"),
        ((2.0, 0.0, 0), "L1"),
        ((2.0, 1.0, 1), "L2"),
        ((4.0, 1.0, 1), "L2"),
        ((4.0, 2.0, 2), "L3"),
        ((6.0, 2.0, 2), "L3"),
    )
    graph = nx.MultiDiGraph()
    for node, level_id in nodes:
        graph.add_node(node, x=node[0], y=node[1], level_ids={level_id})
    _edge(graph, nodes[0][0], nodes[1][0], "P1", length=2.0, level_id="L1")
    _edge(graph, nodes[1][0], nodes[2][0], "E12", mode="elevator", level_id="L1")
    graph.edges[nodes[1][0], nodes[2][0], "E12"].update(
        level_id_from="L1", level_id_to="L2"
    )
    _edge(graph, nodes[2][0], nodes[3][0], "P2", length=2.0, level_id="L2")
    _edge(graph, nodes[3][0], nodes[4][0], "E23", mode="elevator", level_id="L2")
    graph.edges[nodes[3][0], nodes[4][0], "E23"].update(
        level_id_from="L2", level_id_to="L3"
    )
    _edge(graph, nodes[4][0], nodes[5][0], "P3", length=2.0, level_id="L3")
    return _service(
        graph,
        [
            _unit("U-A", "A", "L1", 0.0, 0.0),
            _unit("U-B", "B", "L3", 6.0, 2.0),
        ],
    )


def test_route_geometry_covers_every_edge_and_attributes_transitions_to_both_floors():
    response = _multi_transition_service().route("U-A", "U-B", "default")
    levels_by_edge: dict[str, set[str]] = {}
    for geometry in response["geometries"]:
        levels_by_edge.setdefault(geometry["edge_id"], set()).add(geometry["level_id"])

    assert response["status"] == 200
    assert set(levels_by_edge) == set(response["edge_ids"])
    assert levels_by_edge["E12"] == {"L1", "L2"}
    assert levels_by_edge["E23"] == {"L2", "L3"}


def test_each_transition_exit_step_uses_that_edges_destination_level():
    response = _multi_transition_service().route("U-A", "U-B", "default")
    exit_levels = {
        step["edge_id"]: step["level_id"]
        for step in response["steps"]
        if step["type"] == "exit_transition"
    }

    assert response["status"] == 200
    assert exit_levels == {"E12": "L2", "E23": "L3"}


def test_route_fails_closed_when_selected_edge_has_no_measured_geometry():
    graph = _base_graph()
    graph.edges[(0.0, 0.0, 0), (2.0, 0.0, 0), "P1"].pop("geometry")

    response = _service(graph).route("U-A", "U-B", "default")

    assert response["status"] == 503
    assert response["code"] == "route_validation_failed"


def test_elevator_only_excludes_stairs_even_when_stairs_are_shorter():
    graph = _base_graph()
    _edge(
        graph,
        (0.0, 0.0, 0),
        (2.0, 2.0, 1),
        "S1",
        mode="stairs",
        length=0.1,
    )
    service = _service(graph)

    response = service.route("U-A", "U-C", "elevator_only")

    assert response["status"] == 200
    assert all(edge["mode"] != "stairs" for edge in response["edges"])
    assert response["allowed_modes"] == ALLOWED_MODES["elevator_only"]
    _assert_elevator_disclosure(response)


def test_route_revalidates_returned_edges_against_profile():
    graph = _base_graph()
    _edge(
        graph,
        (0.0, 0.0, 0),
        (2.0, 2.0, 1),
        "BAD",
        mode="outdoor",
        length=0.1,
    )

    response = _service(graph).route("U-A", "U-C", "default")

    assert response["status"] == 200
    assert "BAD" not in response["edge_ids"]
    assert all(edge["mode"] in ALLOWED_MODES["default"] for edge in response["edges"])


@pytest.mark.parametrize(
    ("profile", "expected_code"),
    [("default", "disconnected"), ("elevator_only", "no_elevator_only_route")],
)
def test_disconnected_failure_envelopes_are_profile_specific(
    profile: str,
    expected_code: str,
):
    graph = nx.MultiDiGraph()
    for x in (0.0, 20.0):
        graph.add_node((x, 0.0, 0), x=x, y=0.0, level_ids={"L1"})
    service = _service(
        graph,
        [_unit("U-A", "A", "L1", 0.0, 0.0), _unit("U-B", "B", "L1", 20.0, 0.0)],
    )

    response = service.route("U-A", "U-B", profile)

    assert response["status"] == 409
    assert response["code"] == expected_code
    assert response["profile"] == profile
    _assert_provenance(response)
    if profile == "elevator_only":
        _assert_elevator_disclosure(response)


def test_endpoint_failure_envelope_includes_reason_distance_warnings_and_provenance():
    response = _service(
        units=[
            _unit("U-A", "A", "L1", 0.0, 0.0),
            _unit("U-FAR", "FAR", "L1", 30.0, 0.0),
        ]
    ).route("U-A", "U-FAR", "default")

    assert response["status"] == 422
    assert response["code"] == "endpoint_unavailable"
    assert response["destination"]["unavailable_reason"] == "attachment_over_limit"
    assert response["destination"]["attachment_distance_m"] > 10
    assert "room-to-anchor traversal is not represented or verified" in response["warnings"]
    _assert_provenance(response)


@pytest.mark.parametrize(
    ("origin", "destination", "profile", "status", "code"),
    [
        ("missing", "U-A", "default", 404, "unknown_endpoint"),
        ("U-A", "missing", "default", 404, "unknown_endpoint"),
        ("U-A", "U-B", "invalid", 400, "invalid_profile"),
    ],
)
def test_route_failure_envelopes_cover_unknown_endpoints_and_profiles(
    origin: str,
    destination: str,
    profile: str,
    status: int,
    code: str,
):
    response = _service().route(origin, destination, profile)

    assert response["status"] == status
    assert response["code"] == code
    _assert_provenance(response)


@contextmanager
def _running_server():
    module = importlib.import_module("wayfinding.demo.server")
    server = module.create_server(
        "127.0.0.1",
        0,
        GPKG_PATH,
        GRAPH_PATH,
        STATS_PATH,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(base_url: str, path: str, payload: Any) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({}, 400),
        ({"origin": {"unit_id": "U"}, "destination": {"unit_id": "V"}}, 400),
        ({"origin": "U", "destination": {"unit_id": "V"}, "profile": "default"}, 400),
        ({"origin": {"unit_id": "U"}, "destination": {}, "profile": "default"}, 400),
        ({"origin": {"unit_id": "U"}, "destination": {"unit_id": "V"}, "profile": "fast"}, 400),
        ({"origin": {"unit_id": "U", "extra": 1}, "destination": {"unit_id": "V"},
          "profile": "default"}, 400),
    ],
)
def test_route_http_endpoint_rejects_unbounded_or_invalid_contracts(payload: Any, status: int):
    with _running_server() as base_url:
        actual_status, response = _post(base_url, "/demo/v1/route", payload)

    assert actual_status == status
    assert response["code"] == "invalid_request"
    _assert_provenance(response)


def test_route_http_endpoint_is_post_only_and_future_namespace_stays_absent():
    with _running_server() as base_url:
        for path, expected in (("/demo/v1/route", 405), ("/v1/route", 404)):
            request = urllib.request.Request(f"{base_url}{path}", method="GET")
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            assert caught.value.code == expected


def test_route_http_replays_real_success_and_disconnected_evidence():
    evidence = _load_evidence()
    cases = (
        evidence["pairs"]["default_success"],
        evidence["pairs"]["default_disconnected"],
    )
    with _running_server() as base_url:
        for pair in cases:
            status, response = _post(
                base_url,
                "/demo/v1/route",
                {
                    "origin": {"unit_id": pair["origin_unit_id"]},
                    "destination": {"unit_id": pair["destination_unit_id"]},
                    "profile": "default",
                },
            )
            assert status == pair["expected_status"]
            assert response.get("code") == pair.get("expected_code")
            _assert_provenance(response)


def test_health_advertises_only_the_new_bounded_route_capability():
    with _running_server() as base_url:
        with urllib.request.urlopen(f"{base_url}/demo/v1/health") as response:
            body = json.load(response)

    assert body["capabilities"] == {
        "routing": True,
        "nearest": False,
        "live_status": False,
        "llm": False,
    }
    _assert_provenance(body)


def test_assistant_delegates_exact_directions_and_mobility_forces_elevator_only():
    evidence = _load_evidence()
    pair = evidence["pairs"]["elevator_only_success"]
    repository_module = importlib.import_module("wayfinding.demo.artifact")
    assistant = importlib.import_module("wayfinding.demo.assistant")
    repository = repository_module.ArtifactRepository(GPKG_PATH)
    service = _real_service()
    ordinary = assistant.respond(
        repository,
        f"directions from {pair['origin_unit_id']} to {pair['destination_unit_id']}",
        routing_service=service,
    )
    mobility = assistant.respond(
        repository,
        f"wheelchair directions from {pair['origin_unit_id']} to {pair['destination_unit_id']}",
        routing_service=service,
    )

    assert ordinary == service.route(pair["origin_unit_id"], pair["destination_unit_id"], "default")
    assert mobility == service.route(
        pair["origin_unit_id"], pair["destination_unit_id"], "elevator_only"
    )
    _assert_elevator_disclosure(mobility)


def test_assistant_passes_no_route_response_through_verbatim():
    evidence = _load_evidence()
    pair = evidence["pairs"]["default_disconnected"]
    repository = importlib.import_module("wayfinding.demo.artifact").ArtifactRepository(GPKG_PATH)
    assistant = importlib.import_module("wayfinding.demo.assistant")
    service = _real_service()
    direct = service.route(pair["origin_unit_id"], pair["destination_unit_id"], "default")

    delegated = assistant.respond(
        repository,
        f"directions from {pair['origin_unit_id']} to {pair['destination_unit_id']}",
        routing_service=service,
    )

    assert delegated == direct
    assert delegated["code"] == "disconnected"


def test_assistant_passes_real_ambiguous_endpoint_response_through_verbatim():
    repository = importlib.import_module("wayfinding.demo.artifact").ArtifactRepository(GPKG_PATH)
    assistant = importlib.import_module("wayfinding.demo.assistant")
    service = _real_service()
    labels: dict[str, list[str]] = {}
    for unit in repository.units():
        if unit["room_id"]:
            labels.setdefault(unit["room_id"], []).append(unit["unit_id"])
    ambiguous = min(label for label, unit_ids in labels.items() if len(unit_ids) > 1)
    destination = min(
        unit["unit_id"] for unit in repository.units() if unit["room_id"] != ambiguous
    )
    direct = service.route(ambiguous, destination, "default")

    delegated = assistant.respond(
        repository,
        f"directions from {ambiguous} to {destination}",
        routing_service=service,
    )

    assert direct["code"] == "ambiguous_endpoint"
    assert delegated == direct


def _load_evidence() -> dict[str, Any]:
    assert EVIDENCE_PATH.is_file(), "Data QA must check in docs/reports/DT-014-route-evidence.json"
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


@pytest.mark.dataqa
def test_real_artifact_representative_pairs_are_deterministic_and_replayable():
    evidence = _load_evidence()
    assert evidence["selection_algorithm"] == (
        "lexicographically first eligible distinct unit pair by profile and expected outcome"
    )
    assert evidence["artifact_hashes"] == {
        "gpkg_sha256": _hash(GPKG_PATH),
        "graph_sha256": _hash(GRAPH_PATH),
        "stats_sha256": _hash(STATS_PATH),
    }
    assert set(evidence["pairs"]) == {
        "default_success",
        "default_disconnected",
        "elevator_only_success",
        "elevator_only_disconnected",
    }
    service = _real_service()
    selected_first = service.representative_pairs()
    selected_second = service.representative_pairs()
    assert selected_first == selected_second
    for name, pair in evidence["pairs"].items():
        profile = "elevator_only" if name.startswith("elevator_only") else "default"
        assert {
            "origin_unit_id": pair["origin_unit_id"],
            "destination_unit_id": pair["destination_unit_id"],
        } == selected_first[name]
        first = service.route(pair["origin_unit_id"], pair["destination_unit_id"], profile)
        second = service.route(pair["origin_unit_id"], pair["destination_unit_id"], profile)
        assert first == second
        assert first["status"] == pair["expected_status"]
        assert first.get("code") == pair.get("expected_code")
        assert first["origin"]["component_id"] == pair["origin_component_id"]
        assert first["destination"]["component_id"] == pair["destination_component_id"]
        if first["status"] == 200:
            assert first["edge_ids"] == pair["edge_ids"]
            assert first["network_distance_m"] == pytest.approx(pair["network_distance_m"])
            assert all(edge["mode"] in ALLOWED_MODES[profile] for edge in first["edges"])
            assert pair["edges"] == first["edges"]
            assert pair["geometries"] == first["geometries"]
            for endpoint_name in ("origin", "destination"):
                assert pair[endpoint_name]["unit_id"] == first[endpoint_name]["unit_id"]
                assert pair[endpoint_name]["level_id"] == first[endpoint_name]["level_id"]
                assert pair[endpoint_name]["anchor_node"] == list(
                    first[endpoint_name]["anchor_node"]
                )
                assert pair[endpoint_name]["attachment_distance_m"] == pytest.approx(
                    first[endpoint_name]["attachment_distance_m"]
                )
