"""Regression contract for exact native multipart pathway reconstruction."""

import pytest
from shapely.geometry import MultiLineString

from wayfinding.etl.multipart import reconstruct_pathway


def test_reversed_part_order_keeps_every_source_segment():
    geom = MultiLineString([[(1, 0, 0), (2, 0, 0)], [(0, 0, 0), (1, 0, 0)]])
    coords, spans = reconstruct_pathway(geom, 1)
    assert coords == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    assert [(s["part_index"], s["start_vertex"], s["end_vertex"]) for s in spans] == [
        (1, 0, 1),
        (0, 0, 1),
    ]


@pytest.mark.parametrize(
    "parts",
    [
        [[(0, 0, 0), (1, 0, 0)], [(2, 0, 0), (3, 0, 0)]],
        [[(0, 0, 0), (1, 0, 0)], [(1, 0, 0), (2, 0, 0)], [(1, 0, 0), (1, 1, 0)]],
        [[(0, 0, 0), (1, 0, 0)], [(1, 0, 0), (0, 0, 0)]],
        [[(0, 0, 0), (1, 0, 0)], [(1, 0, 1), (2, 0, 1)]],
    ],
)
def test_ambiguous_or_disconnected_parts_rejected(parts):
    with pytest.raises(ValueError, match="multipart"):
        reconstruct_pathway(MultiLineString(parts), 1)


def test_unknown_multipart_direction_rejected():
    with pytest.raises(ValueError, match="direction"):
        reconstruct_pathway(MultiLineString([[(0, 0, 0), (1, 0, 0)], [(1, 0, 0), (2, 0, 0)]]), 2)


def test_contraction_retains_unequal_native_join():
    from test_dt022_topology import fixture_graph

    from wayfinding.etl.graph import _traverse_chains

    graph, _, _, _ = fixture_graph(
        [
            ("1", "L", [(0, 0, 0), (1, 0, 0)], 1),
            ("2", "L", [(1.001, 0, 0), (2, 0, 0)], 0.999),
        ]
    )
    boundaries = {(0.0, 0.0, 0), (2.0, 0.0, 0)}
    assert len(_traverse_chains(graph, boundaries)) == 2


def test_contraction_merges_equal_native_join():
    from test_dt022_topology import fixture_graph

    from wayfinding.etl.graph import _traverse_chains

    graph, _, _, _ = fixture_graph(
        [
            ("1", "L", [(0, 0, 0), (1, 0, 0)], 1),
            ("2", "L", [(1, 0, 0), (2, 0, 0)], 1),
        ]
    )
    assert len(_traverse_chains(graph, {(0.0, 0.0, 0), (2.0, 0.0, 0)})) == 1


def test_single_part_keeps_original_orientation():
    from shapely.geometry import LineString

    coords = [(2, 0, 0), (1, 0, 0), (0, 0, 0)]
    result, spans = reconstruct_pathway(LineString(coords))
    assert result == coords
    assert spans[-1] == {"part_index": 0, "start_vertex": 1, "end_vertex": 2}


def test_exact_split_across_part_boundary_preserves_reverse_and_contracted_spans():
    import networkx as nx
    from test_dt022_topology import fixture_graph

    from wayfinding.etl.graph import _add_contracted_chain
    from wayfinding.etl.topology import node_shared_vertices, reverse_spans

    geometry = MultiLineString(
        [
            [(1, 0, 0), (2, 0, 0), (3, 0, 0)],
            [(1, 0, 0), (0, 0, 0)],
        ]
    )
    coords, spans = reconstruct_pathway(geometry, 1)
    graph, mapping, attrs, rows = fixture_graph(
        [
            ("1", "L", coords, 6),
            ("2", "L", [(2, 0, 0), (2, 1, 0)], 1),
        ]
    )
    rows[0]["segment_spans"] = [dict(span, feature_id="1") for span in spans]
    candidate, _ = node_shared_vertices(graph, mapping, attrs, rows, [])
    pieces = sorted(
        [
            (u, v, k, d)
            for u, v, k, d in candidate.edges(keys=True, data=True)
            if d["source_feature_id"] == "1" and not k.endswith("_R")
        ],
        key=lambda e: e[3]["geometry"].coords[0][0],
    )
    assert sum(e[3]["length_3d"] for e in pieces) == 6
    assert [s for e in pieces for s in e[3]["source_spans"]] == rows[0]["segment_spans"]
    assert pieces[0][3]["source_spans"][0]["start_vertex"] == 1
    for u, v, k, data in pieces:
        assert candidate[v][u][k + "_R"]["source_spans"] == reverse_spans(data["source_spans"])
    contracted = nx.MultiDiGraph()
    _add_contracted_chain(
        contracted, candidate, {"start": pieces[0][0], "end": pieces[-1][1], "edges": pieces}
    )
    forward = next(
        d for _, _, k, d in contracted.edges(keys=True, data=True) if not k.endswith("_R")
    )
    assert forward["source_spans"] == rows[0]["segment_spans"]
    assert forward["source_spans_complete"]
    assert list(forward["geometry"].coords) == coords
