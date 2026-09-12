"""Exact-source-vertex noding must connect existing paths without inventing gaps."""

import math

import networkx as nx
import pytest
from shapely.geometry import LineString

from wayfinding.etl import graph as graph_module
from wayfinding.etl.build_semantics import semantic_snapshot
from wayfinding.etl.graph import contract_degree2_chains, round_half_up
from wayfinding.etl.topology import node_shared_vertices


def fixture_graph(rows):
    graph = nx.MultiDiGraph()
    node_map, attrs, pathways = {}, {}, []
    for fid, level, coords, weight in rows:
        nodes = []
        for role, coord in (("start", coords[0]), ("end", coords[-1])):
            node = (round_half_up(coord[0], 2), round_half_up(coord[1], 2), 0)
            node_map[("PW", fid, role)] = node
            attrs[node] = {
                "x": node[0],
                "y": node[1],
                "vertical_order": 0,
                "level_ids": {level},
                "z_min": coord[2],
                "z_max": coord[2],
                "z_mean": coord[2],
            }
            graph.add_node(node, **attrs[node])
            nodes.append(node)
        data = {"feature_id": fid, "level_id": level, "mode": "pathway", "length_3d": weight}
        graph.add_edge(*nodes, key=f"PW_{fid}", geometry=LineString(coords), **data)
        graph.add_edge(
            *reversed(nodes), key=f"PW_{fid}_R", geometry=LineString(coords[::-1]), **data
        )
        pathways.append(
            {
                "feature_id": fid,
                "level_id": level,
                "coordinates": coords,
                "endpoints": [coords[0], coords[-1]],
                "length_3d": weight,
            }
        )
    return graph, node_map, attrs, pathways


def junction_rows():
    return [
        ("1", "L", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)], 2.0),
        ("2", "L", [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0)], 1.0),
    ]


def test_exact_endpoint_to_interior_connects_and_preserves_native_segments():
    graph, mapping, attrs, rows = fixture_graph(junction_rows())
    assert not nx.has_path(graph, (0.0, 0.0, 0), (1.0, 1.0, 0))
    candidate, audit = node_shared_vertices(graph, mapping, attrs, rows, [])
    assert nx.shortest_path_length(candidate, (0.0, 0.0, 0), (1.0, 1.0, 0), weight="length_3d") == 2
    assert not nx.has_path(graph, (0.0, 0.0, 0), (1.0, 1.0, 0)), "input graph stays unchanged"
    assert mapping[("PW", "1", "vertex:1")] == (1.0, 0.0, 0)
    pieces = [
        d
        for _, _, k, d in candidate.edges(keys=True, data=True)
        if d.get("source_feature_id") == "1" and not k.endswith("_R")
    ]
    assert len(pieces) == 2
    assert sum(d["length_3d"] for d in pieces) == 2
    assert [
        tuple(c)
        for d in sorted(pieces, key=lambda d: d["source_spans"][0]["start_vertex"])
        for c in list(d["geometry"].coords)[:-1]
    ] == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert audit["split_feature_count"] == 1


def test_split_preserves_legacy_half_centimetre_endpoint_node():
    rows = [
        ("1", "L", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                     (2.8049999997, 0.0, 0.0)], 2.805),
        ("2", "L", [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0)], 1.0),
    ]
    graph, mapping, attrs, pathways = fixture_graph(rows)
    legacy_end = mapping[("PW", "1", "end")]
    # Model the endpoint identity already sealed by endpoint-v1 independently
    # from how the exact WKB float would round when read again.
    graph = nx.relabel_nodes(graph, {legacy_end: (2.81, 0.0, 0)})
    attrs[(2.81, 0.0, 0)] = attrs.pop(legacy_end)
    attrs[(2.81, 0.0, 0)].update(x=2.81)
    mapping[("PW", "1", "end")] = (2.81, 0.0, 0)
    candidate, _ = node_shared_vertices(graph, mapping, attrs, pathways, [])
    assert mapping[("PW", "1", "end")] in candidate
    assert nx.has_path(candidate, (0.0, 0.0, 0), (2.81, 0.0, 0))


@pytest.mark.parametrize(
    "other",
    [
        ("2", "L", [(1.0, 0.001, 0.0), (1.0, 1.0, 0.0)], 1.0),
        ("2", "L", [(1.0, 0.0, 1.0), (1.0, 1.0, 1.0)], 1.0),
        ("2", "OTHER", [(1.0, 0.0, 0.0), (1.0, 1.0, 0.0)], 1.0),
        ("2", "L", [(1.0, -1.0, 0.0), (1.0, 1.0, 0.0)], 2.0),
    ],
)
def test_no_nearby_different_z_level_or_unrecorded_intersection_join(other):
    graph, mapping, attrs, rows = fixture_graph([junction_rows()[0], other])
    candidate, audit = node_shared_vertices(graph, mapping, attrs, rows, [])
    assert candidate.number_of_edges() == graph.number_of_edges()
    assert audit["split_feature_count"] == 0


def test_new_snapped_cell_collision_is_explicitly_skipped():
    rows = junction_rows() + [("3", "L", [(1.001, 0.0, 0.0), (3.0, 1.0, 0.0)], 3.0)]
    graph, mapping, attrs, pathways = fixture_graph(rows)
    candidate, audit = node_shared_vertices(graph, mapping, attrs, pathways, [])
    assert candidate.number_of_edges() == graph.number_of_edges()
    assert any(item["reason"] == "incompatible_snap_cell" for item in audit["skipped_junctions"])


def test_collision_guard_indexes_the_preserved_legacy_endpoint_cell():
    rows = [
        ("1", "L", [(0.0, 0.0, 0.0), (1.01, 0.0, 0.0), (2.0, 0.0, 0.0)], 2.0),
        ("2", "L", [(1.01, 0.0, 0.0), (1.01, 1.0, 0.0)], 1.0),
        ("3", "L", [(1.0049999997, 0.0, 0.0), (3.0, 1.0, 0.0)], 3.0)
    ]
    graph, mapping, attrs, pathways = fixture_graph(rows)
    native_cell = mapping[("PW", "3", "start")]
    legacy_cell = (1.01, 0.0, 0)
    graph = nx.relabel_nodes(graph, {native_cell: legacy_cell})
    mapping[("PW", "3", "start")] = legacy_cell
    candidate, audit = node_shared_vertices(graph, mapping, attrs, pathways, [])
    assert candidate.number_of_edges() == graph.number_of_edges()
    assert any(item["reason"] == "incompatible_snap_cell" for item in audit["skipped_junctions"])


def test_weight_allocation_conserves_recorded_metric_and_discloses_mismatch():
    rows = junction_rows()
    rows[0] = (*rows[0][:3], 3.0)
    graph, mapping, attrs, pathways = fixture_graph(rows)
    candidate, audit = node_shared_vertices(graph, mapping, attrs, pathways, [])
    weights = [
        d["length_3d"]
        for _, _, k, d in candidate.edges(keys=True, data=True)
        if d.get("source_feature_id") == "1" and not k.endswith("_R")
    ]
    assert math.fsum(weights) == 3
    assert audit["metric_mismatches"][0]["feature_id"] == "1"


def test_split_parallel_features_survive_contraction_with_original_provenance(monkeypatch):
    def check_all_pairs(before, after, protected):
        count = 0
        for start in after:
            for end in after:
                assert nx.shortest_path_length(
                    before, start, end, weight="length_3d"
                ) == pytest.approx(nx.shortest_path_length(after, start, end, weight="length_3d"))
                count += 1
        return {"pairs_tested": count, "max_delta_m": 0}

    monkeypatch.setattr(graph_module, "_validate_shortest_paths", check_all_pairs)
    rows = junction_rows() + [("3", *junction_rows()[0][1:])]
    graph, mapping, attrs, pathways = fixture_graph(rows)
    candidate, _ = node_shared_vertices(graph, mapping, attrs, pathways, [])
    contracted, _ = contract_degree2_chains(candidate, [])
    semantic_snapshot(contracted, [])  # Strict reverse arcs include directed source spans.
    assert (
        nx.shortest_path_length(contracted, (0.0, 0.0, 0), (1.0, 1.0, 0), weight="length_3d") == 2
    )
    forward = [d for _, _, k, d in contracted.edges(keys=True, data=True) if not k.endswith("_R")]
    assert {fid for d in forward for fid in d["original_feature_ids"]} == {"1", "2", "3"}
    for u, v, k, data in contracted.edges(keys=True, data=True):
        if k.endswith("_R"):
            continue
        reverse = contracted[v][u][k + "_R"]
        assert reverse["source_spans"] == [
            dict(s, start_vertex=s["end_vertex"], end_vertex=s["start_vertex"])
            for s in reversed(data["source_spans"])
        ]


@pytest.mark.parametrize("weight", [float("nan"), 0.0, -1.0])
def test_invalid_metric_cannot_be_allocated(weight):
    rows = junction_rows()
    rows[0] = (*rows[0][:3], weight)
    graph, mapping, attrs, pathways = fixture_graph(rows)
    with pytest.raises(ValueError, match="metric"):
        node_shared_vertices(graph, mapping, attrs, pathways, [])
