"""Exact geometry spans and conservative plain-language route guidance."""

import math

import networkx as nx
import pytest
from osgeo import ogr
from shapely.geometry import LineString

from wayfinding.demo import guidance
from wayfinding.demo.routing import RoutingService

LEVELS = {
    "L0": {"label": "AQ 1000", "vertical_order": 0},
    "L2": {"label": "AQ 3000", "vertical_order": 2},
}


def edge(coords, key="path", mode="pathway", level="L0", weight=None):
    source = (coords[0][0], coords[0][1], 0)
    target = (coords[-1][0], coords[-1][1], 0)
    attrs = {"geometry": LineString(coords), "mode": mode, "level_id": level,
             "length_3d": weight if weight is not None else sum(
                 math.dist(a, b) for a, b in zip(coords, coords[1:], strict=False)
             )}
    return source, target, key, attrs


def endpoint(node, room="AQ1003", level="L0"):
    return {"unit_id": "SFU_PRIVATE_TECHNICAL_ID", "room_id": room,
            "anchor_node": node, "level_id": level}


def build(edges, levels=None, nodes=None, origin=None, destination=None):
    if nodes is None:
        nodes = {}
        for source, target, _, attrs in edges:
            for node in (source, target):
                nodes[node] = {"level_ids": {attrs.get("level_id") or "L0"},
                               "vertical_order": node[2]}
    return guidance.build_guidance(
        origin or endpoint(edges[0][0]),
        destination or endpoint(edges[-1][1], "AQ1004"), edges,
        level_metadata=LEVELS if levels is None else levels, node_metadata=nodes,
    )


def walks(result):
    return [step for step in result["steps"] if step["kind"] == "walk"]


def test_within_edge_bend_has_exact_disjoint_segment_spans():
    result = build([edge([(0, 0, 0), (3, 0, 0), (3, 4, 0)])])
    assert result["status"] == "available"
    assert [step["action"] for step in walks(result)] == ["continue", "turn_left"]
    assert [step["distance_m"] for step in walks(result)] == [3, 4]
    assert [step["spans"] for step in walks(result)] == [
        [{"edge_occurrence": 0, "start_segment": 0, "end_segment": 1}],
        [{"edge_occurrence": 0, "start_segment": 1, "end_segment": 2}],
    ]
    assert [item["geometry"]["coordinates"] for item in result["geometries"]] == [
        [[0, 0], [3, 0]], [[3, 0], [3, 4]],
    ]
    assert result["distance_m"] == 7
    assert "AQ1003" in result["steps"][0]["instruction"]
    assert "SFU_" not in str([step["instruction"] for step in result["steps"]])


def test_reverse_traversal_reverses_spans_and_turn():
    result = build([edge([(3, 4, 0), (3, 0, 0), (0, 0, 0)])])
    assert [step["action"] for step in walks(result)] == ["continue", "turn_right"]
    assert [step["distance_m"] for step in walks(result)] == [4, 3]


def test_straight_edges_group_but_keep_occurrence_identity():
    result = build([
        edge([(0, 0, 0), (2, 0, 0)], key="same"),
        edge([(2, 0, 0), (5, 0, 0)], key="same"),
    ])
    assert len(walks(result)) == 1
    assert walks(result)[0]["distance_m"] == 5
    assert [span["edge_occurrence"] for span in walks(result)[0]["spans"]] == [0, 1]
    assert len(set(walks(result)[0]["geometry_ids"])) == 2


def test_short_zigzag_does_not_invent_turn_or_drop_geometry():
    coords = [(0, 0, 0), (2, 0, 0), (2, .1, 0), (4, .1, 0)]
    result = build([edge(coords)])
    assert len(walks(result)) == 1
    assert walks(result)[0]["spans"][0]["end_segment"] == 3
    assert result["geometries"][0]["geometry"]["coordinates"] == [list(p[:2]) for p in coords]
    assert result["distance_m"] == pytest.approx(4.1)


def test_validated_small_weight_difference_is_allocated_without_changing_total():
    result = build([edge([(0, 0, 0), (3, 0, 0), (3, 4, 0)], weight=7.02)])
    assert result["status"] == "available"
    assert walks(result)[0]["distance_m"] == pytest.approx(3 * 7.02 / 7)
    assert sum(step["distance_m"] for step in walks(result)) == pytest.approx(7.02)


def test_mismatched_edge_limits_entire_route_without_repair():
    result = build([
        edge([(0, 0, 0), (3, 0, 0), (3, 4, 0)], weight=2),
        edge([(3, 4, 0), (5, 4, 0)]),
    ])
    assert result["status"] == "limited"
    assert result["distance_m"] is None
    assert result["warnings"]
    assert all(step["distance_m"] is None and step["action"] == "continue"
               for step in walks(result))
    assert not any("Turn" in step["instruction"] for step in result["steps"])
    assert result["geometries"][0]["geometry"]["coordinates"] == [[0, 0], [3, 0], [3, 4]]


def transition(reverse=False):
    start, end = ((0, 0, 0), (0, 0, 2))
    coords = [(0, 0, 0), (0, 0, 10)]
    first, last = "L0", "L2"
    if reverse:
        start, end = end, start
        coords = list(reversed(coords))
        first, last = last, first
    attrs = {"mode": "elevator", "geometry": LineString(coords), "length_3d": 10,
             "level_id_from": first, "level_id_to": last,
             "vertical_order_from": start[2], "vertical_order_to": end[2]}
    nodes = {start: {"level_ids": {first}, "vertical_order": start[2]},
             end: {"level_ids": {last}, "vertical_order": end[2]}}
    return (start, end, "lift", attrs), nodes, first, last


@pytest.mark.parametrize("reverse", [False, True])
def test_express_vertical_elevator_has_two_visible_phases_and_one_distance(reverse):
    item, nodes, first, last = transition(reverse)
    result = build([item], nodes=nodes, origin=endpoint(item[0], level=first),
                   destination=endpoint(item[1], level=last))
    assert result["status"] == "available"
    assert [visit["level_id"] for visit in result["visits"]] == [first, last]
    phases = [step for step in result["steps"] if step["kind"] == "transition"]
    assert [step["phase"] for step in phases] == ["departure", "arrival"]
    assert all(step["distance_m"] is None for step in phases)
    assert len(result["transitions"]) == 1
    assert result["transitions"][0]["distance_m"] == result["distance_m"] == 10
    assert ("down" if reverse else "up") in phases[0]["instruction"]
    assert result["geometries"] == []
    assert all(marker["coordinates"] == [0, 0] for marker in result["markers"])
    assert len(set(phases[0]["marker_ids"] + phases[1]["marker_ids"])) == 2


def test_transition_floor_membership_mismatch_is_not_guessed():
    item, nodes, first, last = transition()
    nodes[item[0]]["level_ids"] = {"L2"}
    result = build([item], nodes=nodes, origin=endpoint(item[0], level=first),
                   destination=endpoint(item[1], level=last))
    assert result["status"] == "limited"
    assert result["transitions"][0]["from_level_id"] is None
    instruction = next(step["instruction"] for step in result["steps"]
                       if step["action"] == "take_elevator")
    assert "up" not in instruction
    assert "down" not in instruction


def test_missing_labels_do_not_expose_technical_ids_or_invent_floor_name():
    result = build([edge([(0, 0, 0), (3, 0, 0)])], levels={})
    assert result["status"] == "limited"
    assert result["visits"][0]["label"] == "Floor not recorded"
    assert all("L0" not in step["instruction"] for step in result["steps"])


def test_same_anchor_has_no_lines_and_two_approximate_endpoint_markers():
    origin = endpoint((1, 2, 0))
    destination = endpoint((1, 2, 0), "AQ1004")
    result = guidance.build_guidance(origin, destination, [], level_metadata=LEVELS,
                                    node_metadata={})
    assert result["distance_m"] == 0
    assert result["geometries"] == []
    assert [step["kind"] for step in result["steps"]] == ["depart", "arrive"]
    assert len(result["markers"]) == 2


def test_capacity_refusal_never_returns_truncated_guidance(monkeypatch):
    monkeypatch.setattr(guidance, "MAX_ROUTE_SEGMENTS", 1)
    result = build([edge([(0, 0, 0), (3, 0, 0), (3, 4, 0)])])
    assert result["status"] == "unavailable"
    assert result["warnings"]
    assert result["distance_m"] is None
    collections = ("visits", "steps", "geometries", "markers", "transitions")
    assert all(result[key] == [] for key in collections)


def test_route_integration_is_additive_and_retains_legacy_steps():
    item = edge([(0, 0, 0), (3, 0, 0)])
    graph = nx.MultiDiGraph()
    for node in item[:2]:
        graph.add_node(node, x=node[0], y=node[1], vertical_order=0, level_ids={"L0"})
    graph.add_edge(item[0], item[1], key=item[2], **item[3], feature_id="1")
    units = [{"unit_id": str(index), "room_id": f"AQ100{index}", "level_id": "L0",
              "centroid": node[:2]} for index, node in enumerate(item[:2])]
    service = RoutingService.from_graph(graph, units, {}, level_metadata=LEVELS)
    result = service.route("0", "1", "default")
    assert result["status"] == 200
    assert result["steps"][1]["instruction"] == "Continue along the measured pathway."
    assert result["edge_ids"] == ["path"]
    assert result["network_distance_m"] == 3
    assert result["guidance"]["status"] == "available"


def test_return_visit_is_not_deduplicated_and_transition_length_is_once():
    upward, nodes, _, _ = transition()
    downward, _, _, _ = transition(True)
    result = build([upward, downward], nodes=nodes, destination=endpoint(downward[1]))
    assert [visit["level_id"] for visit in result["visits"]] == ["L0", "L2", "L0"]
    assert len({visit["visit_id"] for visit in result["visits"]}) == 3
    assert sum(item["distance_m"] for item in result["transitions"]) == result["distance_m"] == 20


def test_step_capacity_aborts_complete_presentation(monkeypatch):
    monkeypatch.setattr(guidance, "MAX_GUIDANCE_STEPS", 2)
    result = build([edge([(0, 0, 0), (3, 0, 0), (3, 4, 0)])])
    assert result["status"] == "unavailable"
    assert result["steps"] == []
    assert result["geometries"] == []


@pytest.mark.parametrize("weight", [0, -1, None, float("inf"), float("nan"), True])
def test_invalid_weight_never_produces_numeric_guidance(weight):
    item = edge([(0, 0, 0), (3, 0, 0)])
    item[3]["length_3d"] = weight
    result = build([item])
    assert result["status"] == "limited"
    assert result["distance_m"] is None
    assert walks(result)[0]["distance_m"] is None


def test_native_2d_geometry_is_preview_only_not_assumed_zero_elevation():
    result = build([edge([(0, 0), (3, 0)])])
    assert result["status"] == "limited"
    assert result["distance_m"] is None
    assert result["geometries"][0]["geometry"]["coordinates"] == [[0, 0], [3, 0]]


def test_invalid_geometry_and_unsupported_mode_refuse_guidance():
    item = edge([(0, 0, 0), (3, 0, 0)])
    item[3]["mode"] = "ramp"
    assert build([item])["status"] == "unavailable"
    item[3]["mode"] = "pathway"
    item[3]["geometry"] = None
    assert build([item])["status"] == "unavailable"


@pytest.mark.parametrize(("degrees", "action"), [(14, "continue"), (30, "bear_left"),
                                           (-60, "turn_right"), (160, "u_turn_left")])
def test_meaningful_bearing_thresholds(degrees, action):
    angle = math.radians(degrees)
    coords = [(0, 0, 0), (2, 0, 0), (2 + 2 * math.cos(angle), 2 * math.sin(angle), 0)]
    result = build([edge(coords)])
    assert walks(result)[-1]["action"] == action


def test_endpoint_without_room_label_uses_safe_copy():
    item = edge([(0, 0, 0), (.2, 0, 0)])
    result = build([item], origin=endpoint(item[0], room=None))
    assert result["steps"][0]["instruction"] == "Start near the selected room."
    assert "less than 1 m" in walks(result)[0]["instruction"]


def test_level_metadata_comes_from_artifact_fields(tmp_path):
    path = tmp_path / "labels.gpkg"
    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    for name, fields, rows in (
        ("facility_26910", ["facility_id", "code", "name"], [["F", "AQ", "Academic Quadrangle"]]),
        ("level_26910", ["level_id", "facility_id", "short_name", "vertical_order"],
         [["L0", "F", "1000", 0], ["L2", "F", "3000", 2]]),
    ):
        layer = dataset.CreateLayer(name, geom_type=ogr.wkbNone)
        for field in fields:
            kind = ogr.OFTInteger if field == "vertical_order" else ogr.OFTString
            layer.CreateField(ogr.FieldDefn(field, kind))
        for row in rows:
            feature = ogr.Feature(layer.GetLayerDefn())
            for key, value in zip(fields, row, strict=True):
                feature.SetField(key, value)
            layer.CreateFeature(feature)
    dataset = None
    assert guidance.load_level_metadata(path) == LEVELS


def test_missing_metadata_layers_is_explicitly_empty(tmp_path):
    path = tmp_path / "no-labels.gpkg"
    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    dataset.CreateLayer("other", geom_type=ogr.wkbNone)
    dataset = None
    assert guidance.load_level_metadata(path) == {}


@pytest.mark.parametrize("mode", ["pathway", "elevator"])
@pytest.mark.parametrize("change", ["shifted", "reversed"])
def test_geometry_must_agree_with_directed_node_endpoints(mode, change):
    item = edge([(0, 0, 0), (3, 0, 0)], mode=mode)
    nodes = {item[0]: {"level_ids": {"L0"}, "vertical_order": 0, "x": 0, "y": 0},
             item[1]: {"level_ids": {"L0"}, "vertical_order": 0, "x": 3, "y": 0}}
    destination = endpoint(item[1])
    if mode == "elevator":
        source, _, key, attrs = item
        target = (3, 0, 2)
        attrs.update(level_id_from="L0", level_id_to="L2", vertical_order_from=0,
                     vertical_order_to=2, length_3d=math.sqrt(109),
                     geometry=LineString([(0, 0, 0), (3, 0, 10)]))
        item = (source, target, key, attrs)
        nodes[target] = {"level_ids": {"L2"}, "vertical_order": 2, "x": 3, "y": 0}
        destination = endpoint(target, level="L2")
    coords = list(item[3]["geometry"].coords)
    if change == "reversed":
        coords = list(reversed(coords))
    else:
        coords = [(x + 1, y + 1, z) for x, y, z in coords]
    item[3]["geometry"] = LineString(coords)
    result = build([item], nodes=nodes, destination=destination)
    assert result["status"] == "unavailable"
    assert result["markers"] == []
    assert result["transitions"] == []
    assert result["geometries"] == []
    assert "endpoint" in " ".join(result["warnings"]).lower()


def test_snapped_endpoint_tolerance_is_euclidean_and_does_not_compare_elevation():
    source, target, key, attrs = edge([(.0049, .0049, 80), (3.0049, .0049, 80)])
    item = ((0, 0, 0), (3, 0, 0), key, attrs)
    assert build([item])["status"] == "available"
    attrs["geometry"] = LineString([(.009, .009, 80), (3.009, .009, 80)])
    assert build([item])["status"] == "unavailable"


def test_node_coordinate_attributes_cannot_disagree_with_node_identity():
    item = edge([(0, 0, 0), (3, 0, 0)])
    nodes = {node: {"level_ids": {"L0"}, "vertical_order": 0,
                    "x": node[0] + 2, "y": node[1]} for node in item[:2]}
    assert build([item], nodes=nodes)["status"] == "unavailable"
