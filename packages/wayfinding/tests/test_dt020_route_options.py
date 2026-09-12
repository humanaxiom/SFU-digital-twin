"""Directed route availability without changing or repeatedly routing the graph."""

import http.client
import json
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import networkx as nx
import pytest
from shapely.geometry import LineString

from wayfinding.demo import server as http_server
from wayfinding.demo.routing import RoutingService


def service():
    graph = nx.MultiDiGraph()
    nodes = {name: (x, 0, 0) for name, x in [("A", 0), ("B", 20), ("C", 40),
                                             ("S", 60), ("D", 100)]}
    for node in nodes.values():
        graph.add_node(node, x=node[0], y=0, level_ids={"L0"})
    for left, right, mode in [("A", "B", "pathway"), ("B", "C", "pathway"),
                               ("B", "C", "elevator"), ("C", "S", "stairs"),
                               ("A", "D", "unsupported")]:
        a, b = nodes[left], nodes[right]
        graph.add_edge(a, b, mode=mode, length_3d=abs(b[0]-a[0]), level_id="L0",
                       geometry=LineString([a, b]))
    units = [{"unit_id": name, "room_id": f"room-{name}", "level_id": "L0",
              "centroid": node[:2]} for name, node in nodes.items()]
    units.extend([
        {"unit_id": "A2", "room_id": "room-A2", "level_id": "L0", "centroid": (0, 0)},
        {"unit_id": "S2", "room_id": "room-S2", "level_id": "L0", "centroid": (60, 0)},
        {"unit_id": "BAD", "room_id": "room-BAD", "level_id": "missing", "centroid": (0, 0)},
        {"unit_id": "FAR", "room_id": "room-FAR", "level_id": "L0", "centroid": (999, 0)},
    ])
    return RoutingService.from_graph(graph, list(reversed(units)), {"graph_sha256": "a" * 64})


def classified(result):
    return {item["unit_id"]: item["availability"] for item in result["destinations"]}


def test_outgoing_reachability_profiles_counts_and_same_anchor(monkeypatch):
    routing = service()
    monkeypatch.setattr(routing, "_shortest_path", lambda *_: pytest.fail("No shortest-path calls"))
    before = list(routing.graph.edges(keys=True))
    result = routing.route_options("A", "default")
    assert result["version"] == "route-options-v1"
    assert result["availability_basis"] == "directed_profile_graph"
    assert result["status"] == 200
    assert result["counts"] == {"connected": 4, "same_anchor": 1,
                                "disconnected": 1, "endpoint_unavailable": 2}
    assert classified(result) == {"A2": "same_anchor", "B": "connected", "C": "connected",
                                  "S": "connected", "S2": "connected", "D": "disconnected",
                                  "BAD": "endpoint_unavailable", "FAR": "endpoint_unavailable"}
    assert [item["unit_id"] for item in result["destinations"]] == sorted(classified(result))
    assert result["provenance"] == dict(routing.provenance)
    assert result["warnings"]
    assert routing.route_options("A", "elevator_only")["counts"] == {
        "connected": 2, "same_anchor": 1, "disconnected": 3, "endpoint_unavailable": 2}
    assert "accessibility" in routing.route_options("A", "elevator_only")
    assert list(routing.graph.edges(keys=True)) == before


def test_weak_component_cannot_imply_reverse_availability():
    routing = service()
    assert routing.endpoint_catalog["A"]["reachability_ids"]["default"] == (
        routing.endpoint_catalog["B"]["reachability_ids"]["default"])
    result = classified(routing.route_options("B", "default"))
    assert result["A"] == result["A2"] == "disconnected"
    assert result["C"] == "connected"


def test_profile_isolated_shared_anchor_is_not_a_walk():
    routing = service()
    assert routing.endpoint_catalog["S"]["component_ids"]["elevator_only"] is None
    result = routing.route_options("S", "elevator_only")
    assert classified(result)["S2"] == "same_anchor"
    assert result["counts"]["connected"] == 0
    assert result["counts"]["same_anchor"] == 1


@pytest.mark.parametrize(("origin", "profile", "status", "code"), [
    ("room-A", "default", 404, "unknown_endpoint"),
    ("unknown", "default", 404, "unknown_endpoint"),
    ("BAD", "default", 422, "endpoint_unavailable"),
    ("FAR", "default", 422, "endpoint_unavailable"),
    ("A", "wheelchair", 400, "invalid_profile"),
])
def test_origin_and_profile_errors(origin, profile, status, code):
    result = service().route_options(origin, profile)
    assert (result["status"], result["code"]) == (status, code)
    assert result["destinations"] == []
    assert result["provenance"]["graph_sha256"] == "a" * 64


@contextmanager
def running_server(routing):
    server = http_server.DemoHTTPServer(("127.0.0.1", 0), http_server.DemoRequestHandler)
    server.routing_service = routing
    server.repository = SimpleNamespace(artifact_sha256="fixture")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def get(server, query, method="GET"):
    connection = http.client.HTTPConnection(*server.server_address, timeout=2)
    try:
        connection.request(method, "/demo/v1/route-options" + query)
        response = connection.getresponse()
        return response.status, json.loads(response.read()), dict(response.getheaders())
    finally:
        connection.close()


def test_http_success_and_query_not_in_logs(capsys):
    with running_server(service()) as server:
        status, body, headers = get(server, "?origin_unit_id=A&profile=default")
    assert status == 200
    assert body["origin_unit_id"] == "A"
    assert body["counts"]["connected"] == 4
    assert headers["Cache-Control"] == "no-store"
    logs = capsys.readouterr().out
    assert "route=/demo/v1/route-options status=200" in logs
    assert "origin_unit_id" not in logs


@pytest.mark.parametrize("query", [
    "", "?origin_unit_id=A", "?profile=default", "?origin_unit_id=&profile=default",
    "?origin_unit_id=A&profile=", "?origin_unit_id=A&profile=default&extra=secret",
    "?origin_unit_id=A&origin_unit_id=B&profile=default",
    "?origin_unit_id=A&profile=default&profile=elevator_only",
    "?origin_unit_id=bad%2Fid&profile=default", "?origin_unit_id=%00&profile=default",
])
def test_http_rejects_bad_query(query):
    with running_server(service()) as server:
        status, body, _ = get(server, query)
    assert status == 400
    assert body["code"] == "invalid_request"


def test_http_profile_unknown_ineligible_and_absent_capability():
    with running_server(service()) as server:
        for query, expected in [
            ("?origin_unit_id=A&profile=bad", (400, "invalid_profile")),
            ("?origin_unit_id=unknown&profile=default", (404, "unknown_endpoint")),
            ("?origin_unit_id=BAD&profile=default", (422, "endpoint_unavailable")),
        ]:
            status, body, _ = get(server, query)
            assert (status, body["code"]) == expected
        assert get(server, "", method="POST")[0] == 405
    with running_server(None) as server:
        status, body, _ = get(server, "?origin_unit_id=A&profile=default")
    assert (status, body["code"]) == (503, "routing_unavailable")
