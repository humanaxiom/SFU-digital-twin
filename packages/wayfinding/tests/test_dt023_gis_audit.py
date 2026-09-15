"""Independent tiny-graph oracle for the Stage 0 evidence generator."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import networkx as nx


def test_ordered_profiles_unavailable_and_same_anchor(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[3] / "tools/dt023_gis_audit.py"
    spec = importlib.util.spec_from_file_location("gis_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, mode="stairs")
    graph.add_edge(1, 2, mode="stairs")  # Parallel edges must not double-count pairs.
    graph.add_node(3)
    endpoints = {}
    for unit, facility, node, eligible in (
        ("a", "A", 1, True), ("a2", "A", 1, True),
        ("b", "B", 2, True), ("c", "C", 3, False),
    ):
        endpoints[unit] = {"unit_id": unit, "level_id": f"opaque-{facility}",
                           "anchor_node": node, "eligible": eligible}
    service = SimpleNamespace(
        graph=graph, endpoint_catalog=endpoints,
        allowed_modes={"default": {"stairs", "pathway"}, "elevator_only": {"pathway"}},
    )
    monkeypatch.setattr(module.RoutingService, "from_artifacts", lambda *args: service)
    monkeypatch.setattr(module, "facility_catalog", lambda _: (
        ["A", "B", "C", "D"], {f"opaque-{f}": f for f in "ABC"},
    ))
    for name in ("wayfinding.gpkg", "graph_contracted.pkl", "graph_contracted_stats.json"):
        (tmp_path / name).write_bytes(b"synthetic")
    rows = {(r["profile"], r["origin"], r["destination"]): r
            for r in module.coverage(tmp_path)["rows"]}
    assert rows["default", "A", "B"]["reachable_ordered_pairs"] == 2
    assert rows["default", "B", "A"]["reachable_ordered_pairs"] == 0
    assert rows["elevator_only", "A", "B"]["reachable_ordered_pairs"] == 0
    assert rows["elevator_only", "A", "A"]["reachable_ordered_pairs"] == 2
    assert rows["default", "A", "C"]["eligible_ordered_pairs"] == 0
    assert rows["default", "A", "C"]["status"] == "partial_source_coverage"
    assert rows["default", "A", "C"]["endpoint_unavailable"] == 2
    assert rows["elevator_only", "A", "A"]["same_anchor"] == 2
    assert rows["elevator_only", "A", "A"]["connected"] == 0
    assert rows["default", "A", "B"]["status"] == "mapped_route"
    assert rows["default", "B", "A"]["status"] == "disconnected"
    assert rows["default", "A", "D"]["total_ordered_pairs"] == 0
    assert rows["default", "A", "D"]["status"] == "unavailable"
    for row in rows.values():
        assert row["total_ordered_pairs"] == sum(row[k] for k in
            ("connected", "disconnected", "same_anchor", "endpoint_unavailable"))
