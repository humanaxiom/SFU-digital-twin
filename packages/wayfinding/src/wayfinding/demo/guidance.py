"""Deterministic presentation spans over existing directed route geometry.

This module never changes route topology, weights or artifact geometry. A small
verified geometry/weight discrepancy may be allocated proportionally; an
unreconciled route is a preview without numeric distances or turn assertions.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeGuard

from osgeo import ogr
from shapely.geometry import LineString

VERSION = "dt018-guidance-v1"
MAX_ROUTE_SEGMENTS = 50_000
MAX_GUIDANCE_STEPS = 2_000
MIN_HEADING_LENGTH_M = 0.5
ABSOLUTE_LENGTH_TOLERANCE_M = 0.05
RELATIVE_LENGTH_TOLERANCE = 0.005
ENDPOINT_XY_TOLERANCE_M = 0.01

_COLLECTIONS = ("visits", "steps", "geometries", "markers", "transitions")
_LENGTH_WARNING = (
    "Mapped geometry does not agree with recorded distance. "
    "Distances and turn instructions are unavailable; use this as a route preview only."
)
_FLOOR_WARNING = (
    "Some floor information is missing or inconsistent. "
    "Check floor changes before using this route preview."
)


class _CapacityExceededError(Exception):
    """Internal abort; no partial collection is returned to the client."""


def load_level_metadata(path: Path) -> dict[str, dict[str, Any]]:
    """Read labels and floor order from the same trusted normalized artifact."""
    dataset = ogr.Open(str(path), 0)
    if dataset is None:
        return {}
    facilities = dataset.GetLayerByName("facility_26910")
    levels = dataset.GetLayerByName("level_26910")
    if facilities is None or levels is None:
        return {}
    names = {
        feature.GetField("facility_id"): feature.GetField("code") or feature.GetField("name")
        for feature in facilities
    }
    result = {}
    for feature in levels:
        name = names.get(feature.GetField("facility_id"))
        short = feature.GetField("short_name")
        label = " ".join(str(value).strip() for value in (name, short) if value)
        if not name or not short:
            label = ""
        result[feature.GetField("level_id")] = {
            "label": label, "vertical_order": feature.GetField("vertical_order"),
        }
    return result


def _empty(status: str = "available", warning: str | None = None) -> dict[str, Any]:
    return {
        "version": VERSION, "status": status, "distance_m": None,
        "warnings": [warning] if warning else [], **{key: [] for key in _COLLECTIONS},
    }


def _room(endpoint: Mapping[str, Any]) -> str:
    label = endpoint.get("room_id")
    if label and not str(label).startswith("SFU_"):
        return str(label).strip()
    return "the selected room"


def _finite(value: Any) -> TypeGuard[float | int]:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _node_xy(node: Any, metadata: Mapping[str, Any]) -> tuple[float, float] | None:
    """Check node coordinate identity; its third tuple value is floor order, not Z."""
    identity = None
    if isinstance(node, tuple) and len(node) >= 2 and all(_finite(value) for value in node[:2]):
        identity = (float(node[0]), float(node[1]))
    if "x" in metadata or "y" in metadata:
        x, y = metadata.get("x"), metadata.get("y")
        if not _finite(x) or not _finite(y):
            return None
        recorded = (float(x), float(y))
        if identity is not None and recorded != identity:
            return None
        return recorded
    return identity


def _action(previous: float, current: float) -> str:
    delta = (current - previous + 180) % 360 - 180
    angle = abs(delta)
    if angle < 15:
        return "continue"
    direction = "left" if delta > 0 else "right"
    prefix = "bear" if angle <= 45 else "turn" if angle <= 135 else "u_turn"
    return f"{prefix}_{direction}"


def _walking_text(action: str, distance: float | None) -> str:
    if distance is None:
        return "Follow the highlighted route."
    amount = f"about {math.floor(distance + 0.5)} m" if distance >= 1 else "less than 1 m"
    if action == "continue":
        return f"Continue for {amount}."
    if action.startswith("u_turn"):
        return f"Turn around, then continue for {amount}."
    verb, direction = action.split("_", 1)
    return f"{verb.capitalize()} {direction}, then continue for {amount}."


def build_guidance(
    origin: Mapping[str, Any],
    destination: Mapping[str, Any],
    edges: list[tuple[Any, Any, Any, dict[str, Any]]],
    *,
    level_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    node_metadata: Mapping[Any, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate complete guidance or explicitly refuse excessive expansion."""
    try:
        return _build_guidance(
            origin, destination, edges, level_metadata=level_metadata, node_metadata=node_metadata,
        )
    except _CapacityExceededError:
        return _empty("unavailable", "This route needs too many instructions to display safely.")


def _build_guidance(
    origin: Mapping[str, Any],
    destination: Mapping[str, Any],
    edges: list[tuple[Any, Any, Any, dict[str, Any]]],
    *,
    level_metadata: Mapping[str, Mapping[str, Any]] | None,
    node_metadata: Mapping[Any, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Return bounded response-local visits, steps, markers and exact XY spans.

    Segment ranges are half-open in directed coordinate order: [start, end)
    references coordinates[start:end + 1]. Short segments retain their geometry
    and allocated length but do not establish a direction bearing.
    """
    levels = level_metadata or {}
    nodes = node_metadata or {}
    warnings: list[str] = []

    def warn(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    def floor_label(level: str | None) -> str:
        label = levels.get(level or "", {}).get("label")
        if not isinstance(label, str) or not label.strip():
            warn(_FLOOR_WARNING)
            return "Floor not recorded"
        return label.strip()

    def valid_floor(level: Any, node: Any, declared_order: Any = None) -> str | None:
        metadata = levels.get(level, {}) if isinstance(level, str) else {}
        actual = nodes.get(node, {})
        order = metadata.get("vertical_order")
        if (
            not isinstance(level, str) or not level
            or not isinstance(order, int) or isinstance(order, bool)
            or actual.get("vertical_order") != order
            or level not in actual.get("level_ids", ())
            or (isinstance(node, tuple) and len(node) == 3 and node[2] != order)
            or (declared_order is not None and declared_order != order)
        ):
            warn(_FLOOR_WARNING)
            return None
        floor_label(level)
        return level

    # Validate the entire route before generating any confident numeric/turn copy.
    prepared = []
    segment_count = 0
    for occurrence, (source, target, _key, data) in enumerate(edges):
        geometry = data.get("geometry")
        if not isinstance(geometry, LineString) or geometry.is_empty:
            return _empty("unavailable", "Route geometry is unavailable; cannot show directions.")
        segment_count += len(geometry.coords) - 1
        if segment_count > MAX_ROUTE_SEGMENTS:
            return _empty("unavailable", "This route is too detailed to display directions safely.")
        coords = [list(point) for point in geometry.coords]
        if any(len(point) < 2 or not all(_finite(value) for value in point) for point in coords):
            return _empty("unavailable", "Route coordinates are invalid; cannot show directions.")
        source_xy = _node_xy(source, nodes.get(source, {}))
        target_xy = _node_xy(target, nodes.get(target, {}))
        if (
            source_xy is None or target_xy is None
            or math.dist(coords[0][:2], source_xy) > ENDPOINT_XY_TOLERANCE_M
            or math.dist(coords[-1][:2], target_xy) > ENDPOINT_XY_TOLERANCE_M
        ):
            return _empty(
                "unavailable",
                "Route geometry does not match its directed endpoints; cannot show directions.",
            )
        raw_weight = data.get("length_3d")
        weight = float(raw_weight) if _finite(raw_weight) else math.nan
        segment_lengths = [math.dist(first[:3], second[:3])
                           for first, second in zip(coords, coords[1:], strict=False)]
        geometry_length = math.fsum(segment_lengths)
        valid_length = (
            geometry.has_z and all(len(point) >= 3 for point in coords)
            and _finite(weight) and weight > 0 and geometry_length > 0
            and abs(geometry_length - weight) <= max(
                ABSOLUTE_LENGTH_TOLERANCE_M, RELATIVE_LENGTH_TOLERANCE * weight,
            )
        )
        if not valid_length:
            warn(_LENGTH_WARNING)
        allocations = ([length * weight / geometry_length for length in segment_lengths]
                       if valid_length else [None] * len(segment_lengths))
        mode = data.get("mode")
        if mode not in {"pathway", "stairs", "elevator"}:
            return _empty("unavailable", "The route contains an unsupported movement type.")
        item = {
            "occurrence": occurrence, "coords": coords, "allocations": allocations,
            "mode": mode, "weight": weight, "level_id": data.get("level_id"),
        }
        if mode == "pathway":
            if valid_floor(data.get("level_id"), source) is None or (
                valid_floor(data.get("level_id"), target) is None
            ):
                item["level_id"] = None
        else:
            item["from_level"] = valid_floor(
                data.get("level_id_from"), source, data.get("vertical_order_from"),
            )
            item["to_level"] = valid_floor(
                data.get("level_id_to"), target, data.get("vertical_order_to"),
            )
            if item["from_level"] == item["to_level"]:
                warn(_FLOOR_WARNING)
        prepared.append(item)
    floor_label(origin.get("level_id"))
    floor_label(destination.get("level_id"))
    limited = bool(warnings)
    result = _empty("limited" if limited else "available")
    result["warnings"] = warnings
    result["distance_m"] = None if limited else math.fsum(item["weight"] for item in prepared)

    def visit(level: str | None, *, force: bool = False) -> dict[str, Any]:
        visits = result["visits"]
        if not visits or force or visits[-1]["level_id"] != level:
            visits.append({"visit_id": f"visit-{len(visits)}", "level_id": level,
                           "label": floor_label(level), "step_ids": []})
        return visits[-1]

    def marker(kind: str, level: str | None, coords: Any, label: str) -> str | None:
        if not isinstance(coords, (tuple, list)) or len(coords) < 2:
            return None
        if not all(_finite(value) for value in coords[:2]):
            return None
        identifier = f"marker-{len(result['markers'])}"
        result["markers"].append({"marker_id": identifier, "level_id": level, "kind": kind,
                                  "label": label, "coordinates": list(coords[:2])})
        return identifier

    def step(kind: str, action: str, instruction: str, owner: dict[str, Any], **extra: Any) -> None:
        if len(result["steps"]) >= MAX_GUIDANCE_STEPS:
            raise _CapacityExceededError
        identifier = f"step-{len(result['steps'])}"
        result["steps"].append({
            "step_id": identifier, "kind": kind, "action": action, "instruction": instruction,
            "level_id": owner["level_id"], "visit_id": owner["visit_id"],
            "geometry_ids": [], "marker_ids": [], "spans": [], "distance_m": None,
            "transition_id": None, "phase": None, **extra,
        })
        owner["step_ids"].append(identifier)

    origin_visit = visit(origin.get("level_id"))
    origin_marker = marker("origin", origin.get("level_id"), origin.get("anchor_node"),
                           f"Start near {_room(origin)}")
    step("depart", "start", f"Start near {_room(origin)}.", origin_visit,
         marker_ids=[origin_marker] if origin_marker else [])

    def flush_walk(items: list[dict[str, Any]]) -> None:
        if not items:
            return
        owner = visit(items[0]["level_id"])
        segments = []
        for item in items:
            pairs = zip(item["coords"], item["coords"][1:], strict=False)
            for index, (first, second) in enumerate(pairs):
                segments.append({"item": item, "index": index, "first": first, "second": second,
                                 "length": item["allocations"][index]})
        boundaries = [(0, "continue")]
        previous_heading = None
        if not limited:
            for index, segment in enumerate(segments):
                first, second = segment["first"], segment["second"]
                dx, dy = second[0] - first[0], second[1] - first[1]
                if math.hypot(dx, dy) < MIN_HEADING_LENGTH_M:
                    continue
                heading = math.degrees(math.atan2(dy, dx))
                if previous_heading is not None:
                    action = _action(previous_heading, heading)
                    if action != "continue":
                        boundaries.append((index, action))
                previous_heading = heading
        if len(result["steps"]) + len(boundaries) > MAX_GUIDANCE_STEPS:
            raise _CapacityExceededError
        for position, (start, action) in enumerate(boundaries):
            end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(segments)
            selected = segments[start:end]
            spans: list[dict[str, int]] = []
            for segment in selected:
                occurrence, index = segment["item"]["occurrence"], segment["index"]
                if spans and spans[-1]["edge_occurrence"] == occurrence:
                    spans[-1]["end_segment"] = index + 1
                else:
                    spans.append({"edge_occurrence": occurrence,
                                  "start_segment": index, "end_segment": index + 1})
            geometry_ids = []
            for span in spans:
                item = prepared[span["edge_occurrence"]]
                coords = item["coords"][span["start_segment"]:span["end_segment"] + 1]
                identifier = f"geometry-{len(result['geometries'])}"
                result["geometries"].append({
                    "geometry_id": identifier, "level_id": owner["level_id"], **span,
                    "geometry": {"type": "LineString", "coordinates": [p[:2] for p in coords]},
                })
                geometry_ids.append(identifier)
            distance = None if limited else math.fsum(segment["length"] for segment in selected)
            step("walk", action, _walking_text(action, distance), owner, spans=spans,
                 geometry_ids=geometry_ids, distance_m=distance)

    walking: list[dict[str, Any]] = []
    for item in prepared:
        if item["mode"] == "pathway":
            if walking and walking[-1]["level_id"] != item["level_id"]:
                flush_walk(walking)
                walking = []
            walking.append(item)
            continue
        flush_walk(walking)
        walking = []
        first, last = item["from_level"], item["to_level"]
        departure = visit(first)
        transition_id = f"transition-{len(result['transitions'])}"
        mode = item["mode"]
        departure_marker = marker(mode, first, item["coords"][0], f"{mode.capitalize()} departure")
        arrival_marker = marker(mode, last, item["coords"][-1], f"{mode.capitalize()} arrival")
        direction = ""
        if first is not None and last is not None:
            difference = levels[last]["vertical_order"] - levels[first]["vertical_order"]
            direction = " up" if difference > 0 else " down" if difference < 0 else ""
        target_label = floor_label(last)
        instruction = (f"Take the {mode}{direction} to {target_label}." if last is not None
                       else f"Take the {mode}; the arrival floor is not recorded.")
        step("transition", f"take_{mode}", instruction, departure,
             transition_id=transition_id, phase="departure",
             marker_ids=[departure_marker] if departure_marker else [])
        arrival = visit(last, force=True)
        step("transition", "exit_transition", f"Exit the {mode} on {target_label}.", arrival,
             transition_id=transition_id, phase="arrival",
             marker_ids=[arrival_marker] if arrival_marker else [])
        result["transitions"].append({
            "transition_id": transition_id, "edge_occurrence": item["occurrence"], "mode": mode,
            "from_level_id": first, "to_level_id": last,
            "from_label": floor_label(first), "to_label": target_label,
            "from_visit_id": departure["visit_id"], "to_visit_id": arrival["visit_id"],
            "departure_marker_id": departure_marker, "arrival_marker_id": arrival_marker,
            "distance_m": None if limited else item["weight"],
        })
    flush_walk(walking)
    destination_visit = visit(destination.get("level_id"))
    destination_marker = marker("destination", destination.get("level_id"),
                                destination.get("anchor_node"), f"End near {_room(destination)}")
    step("arrive", "arrive", f"The mapped route ends near {_room(destination)}.", destination_visit,
         marker_ids=[destination_marker] if destination_marker else [])
    return result
