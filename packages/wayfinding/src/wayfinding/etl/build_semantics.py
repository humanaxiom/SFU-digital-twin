"""Canonical semantics for trusted, isolated legacy builds; never loads pickles.

Byte identities belong to the build manifest. These signatures preserve numerical
values, directed parallel edges and ordered geometry while ignoring container
ordering. Reachability uses the existing approximate-anchor routing contract.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

import networkx as nx
import rfc8785
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

from wayfinding.demo.routing import ALLOWED_MODES, RoutingService
from wayfinding.etl.topology import reverse_spans

ALGORITHM_VERSION = "dt016-build-semantics-v1"


def _normalise(value: Any) -> Any:
    """Preserve mapping/set types without user-attribute tag collisions."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Semantic values must be finite")
        return value
    if isinstance(value, BaseGeometry):
        return {"type": "geometry", "value": _normalise(value.__geo_interface__)}
    if isinstance(value, Mapping):
        entries = [[_normalise(key), _normalise(item)] for key, item in value.items()]
        return {"type": "mapping", "entries": sorted(entries, key=rfc8785.dumps)}
    if isinstance(value, (set, frozenset)):
        return {"type": "set", "items": sorted(map(_normalise, value), key=rfc8785.dumps)}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    raise ValueError(f"Unsupported semantic value type: {type(value).__name__}")


def _canonical(value: Any) -> bytes:
    try:
        return rfc8785.dumps(_normalise(value))
    except (TypeError, OverflowError, rfc8785.CanonicalizationError) as error:
        raise ValueError("Cannot canonicalize semantic value") from error


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _report_value(value: Any) -> Any:
    """Convert the routing catalog's immutable mappings to plain JSON data."""
    if isinstance(value, Mapping):
        return {key: _report_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_report_value(item) for item in value]
    return value


def _validate_graph(graph: nx.MultiDiGraph) -> None:
    if not isinstance(graph, nx.MultiDiGraph):
        raise ValueError("A directed multigraph is required")
    forward: Counter[bytes] = Counter()
    reverse: Counter[bytes] = Counter()
    for node, attrs in graph.nodes(data=True):
        if not isinstance(node, tuple) or len(node) != 3:
            raise ValueError("Node identity must be (x, y, vertical_order)")
        if (
            not isinstance(node[2], int) or isinstance(node[2], bool)
            or attrs.get("vertical_order") != node[2]
            or attrs.get("x") != node[0] or attrs.get("y") != node[1]
            or not isinstance(attrs.get("level_ids"), (set, frozenset, list, tuple))
            or not attrs["level_ids"]
            or not all(isinstance(level, str) and level for level in attrs["level_ids"])
        ):
            raise ValueError("Graph node attributes violate the anchor identity contract")
        for coordinate in node[:2]:
            if isinstance(coordinate, bool) or not isinstance(coordinate, (float, int)):
                raise ValueError("Graph coordinates must be finite numbers")
            if not math.isfinite(coordinate):
                raise ValueError("Graph coordinates must be finite numbers")
    for source, target, _key, attrs in graph.edges(keys=True, data=True):
        length = attrs.get("length_3d")
        geometry = attrs.get("geometry")
        if (
            attrs.get("mode") not in ALLOWED_MODES["default"]
            or isinstance(length, bool) or not isinstance(length, (int, float))
            or not math.isfinite(length) or length <= 0
            or not isinstance(geometry, LineString) or geometry.is_empty
        ):
            raise ValueError("Graph edge has unsupported mode, weight or geometry")
        reversed_attrs = dict(attrs)
        reversed_attrs["geometry"] = LineString(list(reversed(geometry.coords)))
        if "source_spans" in attrs:
            reversed_attrs["source_spans"] = reverse_spans(attrs["source_spans"])
        for first, second in (
            ("level_id_from", "level_id_to"),
            ("vertical_order_from", "vertical_order_to"),
        ):
            if first in attrs or second in attrs:
                if first not in attrs or second not in attrs:
                    raise ValueError("Transition endpoint attributes must be paired")
                reversed_attrs[first], reversed_attrs[second] = attrs[second], attrs[first]
        forward[_canonical([source, target, attrs])] += 1
        reverse[_canonical([target, source, reversed_attrs])] += 1
    if forward != reverse:
        raise ValueError("Graph requires matching reverse arcs, modes, weights and geometry")


def _pairs(count: int) -> int:
    return count * (count - 1) // 2


def semantic_snapshot(graph: nx.MultiDiGraph, units: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe already trusted in-memory artifacts without changing them.

    Weak components prove pair reachability here because matching reverse arcs
    are verified, including modes, positive weights and reversed geometry.
    """
    _validate_graph(graph)
    identifiers = [unit.get("unit_id") for unit in units]
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers):
        raise ValueError("Unit IDs must be nonempty strings")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate unit IDs cannot form a deterministic catalog")
    for unit in units:
        centroid = unit.get("centroid")
        if centroid is not None and (
            not isinstance(centroid, (tuple, list)) or len(centroid) != 2
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(item) for item in centroid)
        ):
            raise ValueError("Unit centroid must be a finite XY pair or absent")
    graph_payload = {
        "metadata": graph.graph,
        "nodes": sorted(graph.nodes(data=True), key=lambda item: _canonical(item[0])),
        "edges": sorted(graph.edges(keys=True, data=True), key=lambda item: _canonical(item[:3])),
    }
    graph_hash = _digest(graph_payload)
    unit_hash = _digest(sorted(units, key=lambda unit: unit["unit_id"]))
    service = RoutingService.from_graph(
        graph, units, {"source_status": "isolated legacy build; not promoted"},
    )
    anchors = _report_value(service.endpoint_catalog)
    eligible = sum(bool(endpoint["eligible"]) for endpoint in anchors.values())
    profiles = {}
    for profile in ALLOWED_MODES:
        groups: dict[str, list[str]] = defaultdict(list)
        for unit_id, endpoint in anchors.items():
            if endpoint["eligible"]:
                groups[endpoint["reachability_ids"][profile]].append(unit_id)
        partition = sorted(sorted(members) for members in groups.values())
        reachable = sum(_pairs(len(members)) for members in partition)
        profiles[profile] = {
            "component_count": service.component_count(profile),
            "profile_isolated_node_count": service.profile_isolated_count(profile),
            "groups": partition,
            "total_pairs": _pairs(len(units)),
            "eligible_pairs": _pairs(eligible),
            "reachable_pairs": reachable,
            "disconnected_pairs": _pairs(eligible) - reachable,
            "unavailable_pairs": _pairs(len(units)) - _pairs(eligible),
        }
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "graph_sha256": graph_hash,
        "units_sha256": unit_hash,
        "unit_fingerprints": {
            unit["unit_id"]: _digest(unit)
            for unit in sorted(units, key=lambda unit: unit["unit_id"])
        },
        "anchors_sha256": _digest(anchors),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "unit_count": len(units),
        "eligible_unit_count": eligible,
        "anchors": anchors,
        "profiles": profiles,
    }


def compare_snapshots(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Compare canonical artifacts and exact room-pair reachability partitions."""
    if left.get("algorithm_version") != ALGORITHM_VERSION or (
        right.get("algorithm_version") != ALGORITHM_VERSION
    ):
        raise ValueError("Semantic snapshot algorithm versions must match")
    profiles = {}
    for profile in ALLOWED_MODES:
        left_groups = left["profiles"][profile]["groups"]
        right_groups = right["profiles"][profile]["groups"]
        left_labels = {unit: index for index, group in enumerate(left_groups) for unit in group}
        right_labels = {unit: index for index, group in enumerate(right_groups) for unit in group}
        intersections = Counter(
            (left_labels[unit], right_labels[unit])
            for unit in left_labels.keys() & right_labels.keys()
        )
        shared_pairs = sum(_pairs(count) for count in intersections.values())
        gained = sum(_pairs(len(group)) for group in right_groups) - shared_pairs
        lost = sum(_pairs(len(group)) for group in left_groups) - shared_pairs
        profiles[profile] = {
            "gained_reachable_pairs": gained,
            "lost_reachable_pairs": lost,
            "reachability_equal": gained == 0 and lost == 0,
            "eligible_units_equal": left_labels.keys() == right_labels.keys(),
        }
    graph_equal = left["graph_sha256"] == right["graph_sha256"]
    units_equal = left["units_sha256"] == right["units_sha256"]
    anchors_equal = left["anchors_sha256"] == right["anchors_sha256"]
    all_ids = left["unit_fingerprints"].keys() | right["unit_fingerprints"].keys()
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "equivalent": graph_equal and units_equal and anchors_equal and (
            left["profiles"] == right["profiles"]
        ),
        "graph_equal": graph_equal,
        "units_equal": units_equal,
        "anchors_equal": anchors_equal,
        "changed_unit_ids": sorted(
            unit for unit in all_ids
            if left["unit_fingerprints"].get(unit) != right["unit_fingerprints"].get(unit)
        ),
        "changed_anchor_unit_ids": sorted(
            unit for unit in all_ids if left["anchors"].get(unit) != right["anchors"].get(unit)
        ),
        "profiles": profiles,
    }
