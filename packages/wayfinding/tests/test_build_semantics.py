"""Behavioral evidence for isolated-build semantic comparisons."""

import copy

import networkx as nx
import pytest
from shapely.geometry import LineString

from wayfinding.etl.build_semantics import compare_snapshots, semantic_snapshot


def fixture():
    graph = nx.MultiDiGraph()
    for x in (0, 2, 4):
        graph.add_node((x, 0, 0), x=x, y=0, level_ids={"L", "OTHER"}, vertical_order=0)
    pair(graph, (0, 0, 0), (2, 0, 0), "a")
    pair(graph, (2, 0, 0), (4, 0, 0), "b", mode="stairs")
    units = [
        {"unit_id": str(x), "room_id": str(x), "level_id": "L", "centroid": (x, 0)}
        for x in (0, 2, 4)
    ]
    return graph, units


def pair(graph, source, target, key, mode="pathway", coordinates=None):
    coordinates = coordinates or [source, target]
    for start, end, suffix, coords in (
        (source, target, "", coordinates),
        (target, source, "_R", list(reversed(coordinates))),
    ):
        graph.add_edge(start, end, key=key + suffix, mode=mode, length_3d=2.0,
                       level_id="L", geometry=LineString(coords))


def test_order_is_not_semantics():
    graph, units = fixture()
    reordered = nx.MultiDiGraph()
    for node, attrs in reversed(list(graph.nodes(data=True))):
        reordered.add_node(node, **{**attrs, "level_ids": {"OTHER", "L"}})
    for source, target, key, attrs in reversed(list(graph.edges(keys=True, data=True))):
        reordered.add_edge(source, target, key=key, **attrs)
    assert semantic_snapshot(graph, units) == semantic_snapshot(reordered, list(reversed(units)))


@pytest.mark.parametrize("change", ["parallel", "geometry", "mode", "key", "metadata"])
def test_graph_semantics_preserve_material_changes(change):
    graph, units = fixture()
    baseline = semantic_snapshot(graph, units)
    if change == "parallel":
        pair(graph, (0, 0, 0), (2, 0, 0), "extra")
    elif change == "geometry":
        pair(graph, (0, 0, 0), (2, 0, 0), "a", coordinates=[(0, 0, 0), (1, 1, 0), (2, 0, 0)])
    elif change == "mode":
        pair(graph, (2, 0, 0), (4, 0, 0), "b", mode="elevator")
    elif change == "metadata":
        graph.graph["basis"] = "different"
    else:
        attrs = dict(graph[(0, 0, 0)][(2, 0, 0)]["a"])
        graph.remove_edge((0, 0, 0), (2, 0, 0), "a")
        graph.add_edge((0, 0, 0), (2, 0, 0), key="changed", **attrs)
    result = compare_snapshots(baseline, semantic_snapshot(graph, units))
    assert not result["equivalent"]
    assert not result["graph_equal"]


def test_anchor_and_pair_change():
    graph, units = fixture()
    baseline = semantic_snapshot(graph, units)
    assert baseline["profiles"]["default"]["reachable_pairs"] == 3
    assert baseline["profiles"]["elevator_only"]["reachable_pairs"] == 1
    changed = copy.deepcopy(units)
    changed[2]["centroid"] = (2, 0)
    result = compare_snapshots(baseline, semantic_snapshot(graph, changed))
    assert result["graph_equal"]
    assert result["changed_unit_ids"] == ["4"]
    assert not result["anchors_equal"]
    assert result["profiles"]["elevator_only"]["gained_reachable_pairs"] == 2


def test_unavailable_and_shared_isolated_anchor_pairs():
    graph, units = fixture()
    units.extend([
        {"unit_id": "same", "level_id": "L", "centroid": (4, 0)},
        {"unit_id": "far", "level_id": "L", "centroid": (100, 0)},
    ])
    profile = semantic_snapshot(graph, units)["profiles"]["elevator_only"]
    assert profile["total_pairs"] == 10
    assert profile["eligible_pairs"] == 6
    assert profile["unavailable_pairs"] == 4
    assert profile["reachable_pairs"] == 2
    assert profile["disconnected_pairs"] == 4
    assert profile["component_count"] == 1
    assert profile["profile_isolated_node_count"] == 1


@pytest.mark.parametrize("invalid", ["oneway", "nonfinite", "mode", "reverse", "duplicate"])
def test_invalid_contract_fails_closed(invalid):
    graph, units = fixture()
    if invalid == "oneway":
        graph.remove_edge((2, 0, 0), (0, 0, 0), "a_R")
    elif invalid == "nonfinite":
        graph.graph["bad"] = float("nan")
    elif invalid == "mode":
        graph[(0, 0, 0)][(2, 0, 0)]["a"]["mode"] = "ramp"
    elif invalid == "reverse":
        graph[(2, 0, 0)][(0, 0, 0)]["a_R"]["geometry"] = LineString([(0, 0), (2, 0)])
    else:
        units.append(dict(units[0]))
    with pytest.raises(ValueError, match="reverse arcs|finite|unsupported mode|Duplicate"):
        semantic_snapshot(graph, units)


@pytest.mark.parametrize("weight", [0, -1, float("inf"), float("nan"), "2", True])
def test_invalid_edge_weight(weight):
    graph, units = fixture()
    graph[(0, 0, 0)][(2, 0, 0)]["a"]["length_3d"] = weight
    with pytest.raises(ValueError, match="weight"):
        semantic_snapshot(graph, units)


def test_new_graph_membership_does_not_invent_changed_room_pairs():
    graph, units = fixture()
    baseline = semantic_snapshot(graph, units)
    graph.add_node((6, 0, 0), x=6, y=0, vertical_order=0, level_ids={"L"})
    pair(graph, (4, 0, 0), (6, 0, 0), "new", mode="stairs")
    result = compare_snapshots(baseline, semantic_snapshot(graph, units))
    assert not result["graph_equal"]
    assert not result["anchors_equal"]  # Exact component IDs change with graph membership.
    assert all(profile["reachability_equal"] for profile in result["profiles"].values())


def test_comparison_counts_gained_and_lost_pairs():
    graph, units = fixture()
    baseline = semantic_snapshot(graph, units)
    pair(graph, (2, 0, 0), (4, 0, 0), "b", mode="elevator")
    revised = semantic_snapshot(graph, units)
    assert compare_snapshots(baseline, revised)["profiles"]["elevator_only"] == {
        "gained_reachable_pairs": 2, "lost_reachable_pairs": 0,
        "reachability_equal": False, "eligible_units_equal": True,
    }
    assert compare_snapshots(revised, baseline)["profiles"]["elevator_only"][
        "lost_reachable_pairs"
    ] == 2


def test_unsupported_attribute_and_nonfinite_centroid_fail():
    graph, units = fixture()
    graph.graph["unserializable"] = object()
    with pytest.raises(ValueError, match="Unsupported semantic value"):
        semantic_snapshot(graph, units)
    graph.graph.clear()
    units[0]["centroid"] = (float("inf"), 0)
    with pytest.raises(ValueError, match="finite XY"):
        semantic_snapshot(graph, units)


def test_empty_graph_has_unavailable_endpoints_and_version_mismatch_fails():
    _, units = fixture()
    snapshot = semantic_snapshot(nx.MultiDiGraph(), units)
    assert snapshot["profiles"]["default"]["unavailable_pairs"] == 3
    assert snapshot["profiles"]["default"]["groups"] == []
    with pytest.raises(ValueError, match="algorithm versions"):
        compare_snapshots(snapshot, {**snapshot, "algorithm_version": "unknown"})


def test_changed_unit_reporting_includes_equal_anchor_centroid_change():
    graph, units = fixture()
    units[0]["centroid"] = (0, 1)
    left = semantic_snapshot(graph, units)
    units[0]["centroid"] = (0, -1)
    right = semantic_snapshot(graph, units)
    result = compare_snapshots(left, right)
    assert result["anchors_equal"]
    assert result["changed_unit_ids"] == ["0"]
    assert result["changed_anchor_unit_ids"] == []


def test_typed_mapping_cannot_impersonate_set_or_geometry():
    graph, units = fixture()
    graph.graph["value"] = {"L"}
    set_snapshot = semantic_snapshot(graph, units)
    graph.graph["value"] = {"type": "set", "items": ["L"]}
    mapping_snapshot = semantic_snapshot(graph, units)
    assert set_snapshot["graph_sha256"] != mapping_snapshot["graph_sha256"]
    geometry = LineString([(0, 0, 0), (2, 0, 0)])
    graph.graph["value"] = geometry
    geometry_snapshot = semantic_snapshot(graph, units)
    graph.graph["value"] = {"type": "geometry", "value": geometry.__geo_interface__}
    assert semantic_snapshot(graph, units)["graph_sha256"] != geometry_snapshot["graph_sha256"]
