"""Deterministic bounded routing over the approved DT-014 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import pickle
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import networkx as nx
import rfc8785
from osgeo import ogr

ALGORITHM_VERSION = "dt014-v1"
SOURCE_STATUS = "accepted legacy snapshot; final source-directory lineage pending DT-009"
ALLOWED_MODES = {
    "default": ["elevator", "pathway", "stairs"],
    "elevator_only": ["elevator", "pathway"],
}
NOT_VERIFIED = ["door_width", "path_width", "slope", "powered_doors", "surface"]
WARNINGS = [
    "room-to-anchor traversal is not represented or verified",
    "closures, opening hours, door access, and elevator status are not verified",
]
MAX_IDENTIFIER_LENGTH = 255
MAX_ATTACHMENT_DISTANCE_M = 10.0
REACHABILITY_ALGORITHM = "profile-reachability-rfc8785-sha256-v1"
COMPONENT_SEMANTICS = "edge_induced"


class RouteArtifactError(RuntimeError):
    """Raised when the approved route artifacts fail closed validation."""

    status = 503
    code = "artifact_mismatch"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _node_sort_key(node: Any) -> bytes:
    return _canonical_json(node)


def _canonical_json(value: Any) -> bytes:
    return rfc8785.dumps(value)


def _component_identifier(profile: str, nodes: set[Any]) -> str:
    sorted_nodes = sorted(nodes, key=_canonical_json)
    payload = {"kind": "counted_component", "nodes": sorted_nodes, "profile": profile}
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _isolated_reachability_identifier(profile: str, node: Any) -> str:
    payload = {
        "kind": "profile_isolated_singleton",
        "node": node,
        "profile": profile,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _lineage_hash(stats: dict[str, Any], suffix: str) -> str | None:
    for group in ("inputs", "outputs"):
        for item in stats.get("lineage", {}).get(group, []):
            if str(item.get("path", "")).replace("\\", "/").endswith(suffix):
                return item.get("sha256")
    return None


def _immutable_endpoint(endpoint: dict[str, Any]) -> Mapping[str, Any]:
    endpoint = dict(endpoint)
    for field in ("component_ids", "reachability_ids", "reachability_kinds"):
        values = endpoint.get(field)
        if isinstance(values, dict):
            endpoint[field] = MappingProxyType(dict(values))
    return MappingProxyType(endpoint)


def _positive_length(data: dict[str, Any]) -> float | None:
    raw_length = data.get("length_3d")
    if raw_length is None:
        return None
    try:
        length = float(raw_length)
    except (TypeError, ValueError):
        return None
    return length if math.isfinite(length) and length > 0 else None


def _node_xy(data: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        x = float(data["x"])
        y = float(data["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _units_from_gpkg(path: Path) -> list[dict[str, Any]]:
    dataset = ogr.Open(str(path), 0)
    if dataset is None:
        raise RouteArtifactError("The route GeoPackage could not be opened.")
    layer = dataset.GetLayerByName("unit_26910")
    if layer is None:
        dataset = None
        raise RouteArtifactError("The route GeoPackage is missing unit_26910.")
    units = []
    for feature in layer:
        centroid_wkt = feature.GetField("centroid_26910")
        centroid = ogr.CreateGeometryFromWkt(centroid_wkt) if centroid_wkt else None
        units.append(
            {
                "unit_id": feature.GetField("unit_id"),
                "room_id": feature.GetField("room_id"),
                "level_id": feature.GetField("level_id"),
                "centroid": (centroid.GetX(), centroid.GetY()) if centroid is not None else None,
            }
        )
    dataset = None
    return units


class RoutingService:
    """Route between disclosed room anchors without mutating the source graph."""

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        units: list[dict[str, Any]],
        provenance: dict[str, str],
    ) -> None:
        self.graph = graph
        self.provenance = MappingProxyType(dict(provenance))
        self.allowed_modes = ALLOWED_MODES
        self.component_ids: dict[str, dict[Any, str]] = {}
        for profile, modes in self.allowed_modes.items():
            filtered = nx.MultiDiGraph()
            for source, target, key, data in graph.edges(keys=True, data=True):
                if data.get("mode") in modes:
                    filtered.add_edge(source, target, key=key, **data)
            component_labels: dict[Any, str] = {}
            for component in nx.weakly_connected_components(filtered):
                identifier = _component_identifier(profile, set(component))
                component_labels.update(dict.fromkeys(component, identifier))
            self.component_ids[profile] = component_labels
        self.endpoint_catalog: Mapping[str, Mapping[str, Any]] = MappingProxyType(
            self._build_catalog(units)
        )
        room_labels: dict[str, list[str]] = defaultdict(list)
        for unit in units:
            room_id = unit.get("room_id")
            if room_id:
                room_labels[str(room_id).casefold()].append(str(unit["unit_id"]))
        self._room_labels = {
            label: sorted(unit_ids) for label, unit_ids in room_labels.items()
        }

    @classmethod
    def from_graph(
        cls,
        graph: nx.MultiDiGraph,
        units: list[dict[str, Any]],
        provenance: dict[str, str],
    ) -> RoutingService:
        return cls(graph, units, provenance)

    @classmethod
    def from_artifacts(
        cls,
        gpkg_path: str | Path,
        graph_path: str | Path,
        stats_path: str | Path,
    ) -> RoutingService:
        gpkg = Path(gpkg_path)
        graph_file = Path(graph_path)
        stats_file = Path(stats_path)
        if not all(path.is_file() for path in (gpkg, graph_file, stats_file)):
            raise RouteArtifactError("A required route artifact is unavailable.")
        try:
            stats = json.loads(stats_file.read_text(encoding="utf-8"))
            gpkg_hash = _sha256(gpkg)
            graph_hash = _sha256(graph_file)
            if gpkg_hash != _lineage_hash(stats, "wayfinding.gpkg"):
                raise RouteArtifactError("The GeoPackage lineage hash does not match.")
            if graph_hash != _lineage_hash(stats, "graph_contracted.pkl"):
                raise RouteArtifactError("The graph lineage hash does not match.")
            with graph_file.open("rb") as stream:
                graph = pickle.load(stream)  # noqa: S301 - hash-verified trusted build artifact
            if not isinstance(graph, nx.MultiDiGraph):
                raise TypeError("The contracted graph has an unexpected type.")
            units = _units_from_gpkg(gpkg)
        except RouteArtifactError:
            raise
        except Exception as error:
            raise RouteArtifactError("The route artifacts could not be validated.") from error
        return cls(
            graph,
            units,
            {
                "gpkg_sha256": gpkg_hash,
                "graph_sha256": graph_hash,
                "stats_sha256": _sha256(stats_file),
                "source_status": SOURCE_STATUS,
                "algorithm_version": ALGORITHM_VERSION,
            },
        )

    def component_count(self, profile: str) -> int:
        return len(set(self.component_ids[profile].values()))

    def profile_isolated_count(self, profile: str) -> int:
        return len(set(self.graph.nodes) - set(self.component_ids[profile]))

    def _build_catalog(self, units: list[dict[str, Any]]) -> dict[str, Mapping[str, Any]]:
        nodes_by_level: dict[str, list[Any]] = defaultdict(list)
        for node, data in self.graph.nodes(data=True):
            for level_id in data.get("level_ids", set()):
                nodes_by_level[str(level_id)].append(node)
        for nodes in nodes_by_level.values():
            nodes.sort(key=_node_sort_key)

        catalog: dict[str, Mapping[str, Any]] = {}
        for unit in sorted(units, key=lambda item: str(item["unit_id"])):
            unit_id = str(unit["unit_id"])
            level_id = str(unit.get("level_id") or "")
            endpoint: dict[str, Any] = {
                "unit_id": unit_id,
                "room_id": unit.get("room_id"),
                "level_id": level_id,
                "attachment_distance_m": None,
                "attachment_crs": "EPSG:26910",
                "approximate": True,
                "eligible": False,
            }
            centroid = unit.get("centroid")
            candidates = nodes_by_level.get(level_id, [])
            if centroid is None:
                endpoint["unavailable_reason"] = "missing_centroid"
            elif not candidates:
                endpoint["unavailable_reason"] = "no_same_level_node"
            else:
                ranked = []
                for node in candidates:
                    coordinates = _node_xy(self.graph.nodes[node])
                    if coordinates is None:
                        continue
                    ranked.append(
                        (
                            math.hypot(
                                coordinates[0] - float(centroid[0]),
                                coordinates[1] - float(centroid[1]),
                            ),
                            _node_sort_key(node),
                            node,
                        )
                    )
                if not ranked:
                    endpoint["unavailable_reason"] = "no_same_level_node"
                    catalog[unit_id] = _immutable_endpoint(endpoint)
                    continue
                distance, _key, anchor = min(ranked)
                endpoint["anchor_node"] = anchor
                endpoint["attachment_distance_m"] = distance
                component_ids = {}
                reachability_ids = {}
                reachability_kinds = {}
                for profile in self.allowed_modes:
                    component_id = self.component_ids[profile].get(anchor)
                    component_ids[profile] = component_id
                    reachability_ids[profile] = component_id or (
                        _isolated_reachability_identifier(profile, anchor)
                    )
                    reachability_kinds[profile] = (
                        "counted_component"
                        if component_id is not None
                        else "profile_isolated_singleton"
                    )
                endpoint["component_ids"] = component_ids
                endpoint["reachability_ids"] = reachability_ids
                endpoint["reachability_kinds"] = reachability_kinds
                if distance <= MAX_ATTACHMENT_DISTANCE_M:
                    endpoint["eligible"] = True
                else:
                    endpoint["unavailable_reason"] = "attachment_over_limit"
            catalog[unit_id] = _immutable_endpoint(endpoint)
        return catalog

    def resolve_endpoint(self, identifier: Any) -> dict[str, Any]:
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > MAX_IDENTIFIER_LENGTH
        ):
            return {"status": 400, "code": "invalid_endpoint"}
        if identifier in self.endpoint_catalog:
            return dict(self.endpoint_catalog[identifier])
        matches = self._room_labels.get(identifier.casefold(), [])
        if len(matches) == 1:
            return dict(self.endpoint_catalog[matches[0]])
        if len(matches) > 1:
            return {"status": 409, "code": "ambiguous_endpoint", "matches": matches}
        return {"status": 404, "code": "unknown_endpoint"}

    def _base(self, profile: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profile": profile,
            "allowed_modes": self.allowed_modes.get(profile, []),
            "reachability_algorithm": REACHABILITY_ALGORITHM,
            "component_semantics": COMPONENT_SEMANTICS,
            "component_count": (
                self.component_count(profile) if profile in self.allowed_modes else 0
            ),
            "warnings": list(WARNINGS),
            "provenance": dict(self.provenance),
        }
        if profile == "elevator_only":
            payload["accessibility"] = {
                "basis": "TRANSITION_TYPE=4 (elevator) only; stairs excluded",
                "not_verified": list(NOT_VERIFIED),
            }
        return payload

    def route(
        self,
        origin_identifier: Any,
        destination_identifier: Any,
        profile: str,
    ) -> dict[str, Any]:
        response = self._base(profile)
        if profile not in self.allowed_modes:
            return {**response, "status": 400, "code": "invalid_profile"}
        origin = self.resolve_endpoint(origin_identifier)
        destination = self.resolve_endpoint(destination_identifier)
        for endpoint in (origin, destination):
            if "status" in endpoint:
                return {**response, **endpoint}
        origin = self._route_endpoint(origin, profile)
        destination = self._route_endpoint(destination, profile)
        response.update(origin=origin, destination=destination)
        if not origin["eligible"] or not destination["eligible"]:
            return {**response, "status": 422, "code": "endpoint_unavailable"}
        if origin["reachability_id"] != destination["reachability_id"]:
            code = "no_elevator_only_route" if profile == "elevator_only" else "disconnected"
            return {**response, "status": 409, "code": code, "search_executed": False}

        if (
            origin["reachability_kind"] == "profile_isolated_singleton"
            and origin["anchor_node"] == destination["anchor_node"]
        ):
            return {
                **response,
                "status": 200,
                "crs": "EPSG:26910",
                "search_executed": False,
                "node_ids": [origin["anchor_node"]],
                "edge_ids": [],
                "edges": [],
                "network_distance_m": 0,
                "geometries": [],
                "steps": self._steps(origin, destination, []),
            }

        nodes, selected_edges = self._shortest_path(
            origin["anchor_node"], destination["anchor_node"], profile
        )
        if not self._selected_edges_are_valid(selected_edges, profile):
            return {**response, "status": 503, "code": "route_validation_failed"}
        edges = [
            self._public_edge(source, target, key, data)
            for source, target, key, data in selected_edges
        ]
        return {
            **response,
            "status": 200,
            "crs": "EPSG:26910",
            "search_executed": True,
            "node_ids": nodes,
            "edge_ids": [edge["edge_id"] for edge in edges],
            "edges": edges,
            "network_distance_m": sum(edge["length_3d"] for edge in edges),
            "geometries": self._geometries(selected_edges),
            "steps": self._steps(origin, destination, selected_edges),
        }

    @staticmethod
    def _route_endpoint(endpoint: dict[str, Any], profile: str) -> dict[str, Any]:
        result = dict(endpoint)
        component_ids = result.pop("component_ids", {})
        reachability_ids = result.pop("reachability_ids", {})
        reachability_kinds = result.pop("reachability_kinds", {})
        result["component_id"] = component_ids.get(profile)
        result["reachability_id"] = reachability_ids.get(profile)
        result["reachability_kind"] = reachability_kinds.get(profile)
        return result

    def _shortest_path(
        self, origin: Any, destination: Any, profile: str
    ) -> tuple[list[Any], list[tuple[Any, Any, Any, dict[str, Any]]]]:
        if origin == destination:
            return [origin], []
        allowed = set(self.allowed_modes[profile])
        queue: list[tuple[float, tuple[bytes, ...], bytes, Any, list[Any], list[Any]]] = [
            (0.0, (), _node_sort_key(origin), origin, [origin], [])
        ]
        best: dict[Any, tuple[float, tuple[bytes, ...]]] = {origin: (0.0, ())}
        while queue:
            cost, signature, _node_key, node, nodes, edges = heapq.heappop(queue)
            if best.get(node) != (cost, signature):
                continue
            if node == destination:
                return nodes, edges
            candidates = []
            for _source, target, key, data in self.graph.out_edges(node, keys=True, data=True):
                if data.get("mode") not in allowed:
                    continue
                edge_key = _canonical_json({"edge_key": str(key), "target_node": target})
                candidates.append((edge_key, target, key, data))
            for edge_key, target, key, data in sorted(candidates):
                next_cost = cost + (_positive_length(data) or 0.0)
                next_signature = (*signature, edge_key)
                candidate = (next_cost, next_signature)
                if target not in best or candidate < best[target]:
                    best[target] = candidate
                    heapq.heappush(
                        queue,
                        (
                            next_cost,
                            next_signature,
                            _node_sort_key(target),
                            target,
                            [*nodes, target],
                            [*edges, (node, target, key, data)],
                        ),
                    )
        raise RuntimeError("Component precheck and directed path search disagree.")

    def _selected_edges_are_valid(
        self,
        edges: list[tuple[Any, Any, Any, dict[str, Any]]],
        profile: str,
    ) -> bool:
        for _source, _target, _key, data in edges:
            if (
                data.get("mode") not in self.allowed_modes[profile]
                or data.get("geometry") is None
                or _positive_length(data) is None
            ):
                return False
        return True

    @staticmethod
    def _public_edge(source: Any, target: Any, key: Any, data: dict[str, Any]) -> dict[str, Any]:
        original_feature_ids = list(data.get("original_feature_ids", [data.get("feature_id")]))
        return {
            "edge_id": str(key),
            "source_id": data.get("feature_id") or original_feature_ids[0],
            "original_feature_ids": original_feature_ids,
            "mode": data.get("mode"),
            "length_3d": float(data.get("length_3d", 0.0)),
            "level_id": data.get("level_id"),
            "source_node": list(source) if isinstance(source, tuple) else source,
            "target_node": list(target) if isinstance(target, tuple) else target,
        }

    @staticmethod
    def _edge_coordinates(data: dict[str, Any]) -> list[list[float]]:
        return [[float(x), float(y)] for x, y, *_rest in data["geometry"].coords]

    def _geometries(
        self,
        edges: list[tuple[Any, Any, Any, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        geometries = []
        for source, target, key, data in edges:
            level_ids = self._edge_level_ids(source, target, data)
            for level_id in sorted(str(value) for value in level_ids if value):
                geometries.append(
                    {
                        "level_id": level_id,
                        "edge_id": str(key),
                        "geometry": {
                            "type": "LineString",
                            "coordinates": self._edge_coordinates(data),
                        },
                    }
                )
        return geometries

    def _edge_level_ids(
        self, source: Any, target: Any, data: dict[str, Any]
    ) -> set[str]:
        level_ids = {str(value) for value in data.get("level_ids", []) if value}
        if data.get("mode") in {"stairs", "elevator"}:
            level_ids.update(
                str(value)
                for value in (data.get("level_id_from"), data.get("level_id_to"))
                if value
            )
            for node in (source, target):
                level_ids.update(
                    str(value)
                    for value in self.graph.nodes[node].get("level_ids", set())
                    if value
                )
        elif data.get("level_id"):
            level_ids.add(str(data["level_id"]))
        return level_ids

    @staticmethod
    def _geometry_bearing(data: dict[str, Any], *, departing: bool) -> float | None:
        coordinates = list(data["geometry"].coords)
        pairs = zip(coordinates, coordinates[1:], strict=False)
        if not departing:
            pairs = reversed(list(pairs))
        for first, second in pairs:
            delta_x = float(second[0]) - float(first[0])
            delta_y = float(second[1]) - float(first[1])
            if delta_x or delta_y:
                return math.degrees(math.atan2(delta_y, delta_x))
        return None

    @staticmethod
    def _pathway_instruction(previous: float | None, current: float | None) -> tuple[str, str]:
        if previous is None or current is None:
            return "continue", "Continue along the measured pathway."
        delta = (current - previous + 180.0) % 360.0 - 180.0
        magnitude = abs(delta)
        if magnitude < 15.0:
            return "continue", "Continue along the measured pathway."
        direction = "left" if delta > 0 else "right"
        if magnitude <= 45.0:
            return "turn", f"Bear {direction} along the measured pathway."
        if magnitude <= 135.0:
            return "turn", f"Turn {direction} along the measured pathway."
        return "turn", f"Make a {direction} u-turn along the measured pathway."

    def _node_level(self, node: Any, fallback: Any) -> Any:
        level_ids = sorted(str(value) for value in self.graph.nodes[node].get("level_ids", set()))
        return level_ids[0] if level_ids else fallback

    def _steps(
        self,
        origin: dict[str, Any],
        destination: dict[str, Any],
        edges: list[tuple[Any, Any, Any, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        steps = [
            {
                "type": "depart",
                "level_id": origin["level_id"],
                "instruction": f"Depart from the approximate anchor for {origin['unit_id']}.",
            }
        ]
        previous_pathway_bearing = None
        for source, target, key, data in edges:
            mode = data.get("mode")
            if mode in {"stairs", "elevator"}:
                from_level = data.get("level_id_from") or self._node_level(
                    source, data.get("level_id")
                )
                to_level = data.get("level_id_to") or self._node_level(target, from_level)
                steps.append(
                    {
                        "type": "enter_transition",
                        "level_id": from_level,
                        "edge_id": str(key),
                        "instruction": f"Enter the {mode} transition.",
                    }
                )
                steps.append(
                    {
                        "type": "exit_transition",
                        "level_id": to_level,
                        "edge_id": str(key),
                        "instruction": f"Exit the {mode} transition.",
                    }
                )
                previous_pathway_bearing = None
            else:
                current_bearing = self._geometry_bearing(data, departing=True)
                step_type, instruction = self._pathway_instruction(
                    previous_pathway_bearing, current_bearing
                )
                steps.append(
                    {
                        "type": step_type,
                        "level_id": data.get("level_id") or origin["level_id"],
                        "edge_id": str(key),
                        "instruction": instruction,
                    }
                )
                previous_pathway_bearing = self._geometry_bearing(data, departing=False)
        steps.append(
            {
                "type": "arrive",
                "level_id": destination["level_id"],
                "instruction": f"Arrive at the approximate anchor for {destination['unit_id']}.",
            }
        )
        return steps

    def representative_pairs(self) -> dict[str, dict[str, str]]:
        eligible = [
            unit_id
            for unit_id, endpoint in self.endpoint_catalog.items()
            if endpoint["eligible"]
        ]
        pairs: dict[str, dict[str, str]] = {}
        for profile in self.allowed_modes:
            success = None
            disconnected = None
            for index, origin_id in enumerate(eligible):
                origin = self.endpoint_catalog[origin_id]
                for destination_id in eligible[index + 1 :]:
                    destination = self.endpoint_catalog[destination_id]
                    same = (
                        origin["reachability_ids"][profile]
                        == destination["reachability_ids"][profile]
                    )
                    pair = {
                        "origin_unit_id": origin_id,
                        "destination_unit_id": destination_id,
                    }
                    if (
                        same
                        and success is None
                        and origin["anchor_node"] != destination["anchor_node"]
                    ):
                        success = pair
                    if not same and disconnected is None:
                        disconnected = pair
                    if success and disconnected:
                        break
                if success and disconnected:
                    break
            if success is None or disconnected is None:
                raise RuntimeError(f"No representative {profile} pairs are available.")
            pairs[f"{profile}_success"] = success
            pairs[f"{profile}_disconnected"] = disconnected
        return pairs

    def _profile_isolated_inventory(self, profile: str) -> list[dict[str, Any]]:
        isolated_nodes = set(self.graph.nodes) - set(self.component_ids[profile])
        return [
            {
                "anchor_node": node,
                "reachability_id": _isolated_reachability_identifier(profile, node),
            }
            for node in sorted(isolated_nodes, key=_node_sort_key)
        ]

    def _isolated_same_anchor_pair(self, profile: str) -> dict[str, str] | None:
        units_by_anchor: dict[Any, list[str]] = defaultdict(list)
        for unit_id, endpoint in self.endpoint_catalog.items():
            if (
                endpoint["eligible"]
                and endpoint["reachability_kinds"][profile]
                == "profile_isolated_singleton"
            ):
                units_by_anchor[endpoint["anchor_node"]].append(unit_id)
        candidates = sorted(
            (unit_ids[0], unit_ids[1])
            for unit_ids in (sorted(values) for values in units_by_anchor.values())
            if len(unit_ids) >= 2
        )
        if not candidates:
            return None
        origin_unit_id, destination_unit_id = candidates[0]
        return {
            "origin_unit_id": origin_unit_id,
            "destination_unit_id": destination_unit_id,
        }

    @staticmethod
    def _evidence_pair(
        identifiers: dict[str, str], response: dict[str, Any]
    ) -> dict[str, Any]:
        same_reachability = (
            response["origin"]["reachability_id"]
            == response["destination"]["reachability_id"]
        )
        pair: dict[str, Any] = {
            **identifiers,
            "expected_status": response["status"],
            "http_status": response["status"],
            "origin_component_id": response["origin"]["component_id"],
            "destination_component_id": response["destination"]["component_id"],
            "origin": response["origin"],
            "destination": response["destination"],
            "precheck_result": (
                "same_reachability" if same_reachability else "different_reachability"
            ),
            "shortest_path_invoked": response.get("search_executed", False),
            "edge_count": len(response.get("edges", [])),
            "network_distance_m": response.get("network_distance_m"),
        }
        if "code" in response:
            pair["expected_code"] = response["code"]
        else:
            pair.update(
                edge_ids=response["edge_ids"],
                edges=response["edges"],
                geometries=response["geometries"],
            )
        return pair

    def evidence_document(self) -> dict[str, Any]:
        pairs = {}
        representative_pairs = self.representative_pairs()
        isolated_pair = self._isolated_same_anchor_pair("elevator_only")
        if isolated_pair is not None:
            representative_pairs["elevator_only_profile_isolated_same_anchor"] = isolated_pair
        for name, identifiers in representative_pairs.items():
            profile = "elevator_only" if name.startswith("elevator_only") else "default"
            response = self.route(
                identifiers["origin_unit_id"],
                identifiers["destination_unit_id"],
                profile,
            )
            pairs[name] = self._evidence_pair(identifiers, response)
        isolated_inventory = {
            profile: self._profile_isolated_inventory(profile)
            for profile in self.allowed_modes
        }
        document = {
            "selection_algorithm": (
                "lexicographically first eligible distinct unit pair by profile "
                "and expected outcome"
            ),
            "artifact_hashes": {
                name: value
                for name, value in self.provenance.items()
                if name in {"gpkg_sha256", "graph_sha256", "stats_sha256"}
            },
            "component_counts": {
                profile: self.component_count(profile) for profile in self.allowed_modes
            },
            "profile_isolated_counts": {
                profile: len(nodes) for profile, nodes in isolated_inventory.items()
            },
            "profile_isolated_nodes": isolated_inventory,
            "profile_isolated_anchored_endpoint_counts": {
                profile: sum(
                    endpoint["eligible"]
                    and endpoint["reachability_kinds"][profile]
                    == "profile_isolated_singleton"
                    for endpoint in self.endpoint_catalog.values()
                )
                for profile in self.allowed_modes
            },
            "pairs": pairs,
        }
        document["evidence_sha256"] = hashlib.sha256(_canonical_json(document)).hexdigest()
        return document


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic DT-014 route evidence.")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    service = RoutingService.from_artifacts(
        arguments.artifact,
        arguments.graph,
        arguments.stats,
    )
    arguments.output.write_bytes(_canonical_json(service.evidence_document()))


if __name__ == "__main__":
    main()
