"""Reconstruct source parts without creating segments or guessing connectivity."""

import math
from collections import defaultdict
from typing import Any

from shapely.geometry import LineString, MultiLineString


def reconstruct_pathway(
    geometry: LineString | MultiLineString,
    direction: Any = 1,
) -> tuple[list[Any], list[dict[str, int]]]:
    """Return native coordinates and one original source span per segment."""
    parts = [geometry] if isinstance(geometry, LineString) else list(geometry.geoms)
    coordinates = [list(part.coords) for part in parts]
    if len(parts) == 1:
        return coordinates[0], [
            {"part_index": 0, "start_vertex": i, "end_vertex": i + 1}
            for i in range(len(coordinates[0]) - 1)
        ]
    if direction != 1:
        raise ValueError("unsupported_multipart_direction")
    adjacency: dict[Any, list[int]] = defaultdict(list)
    for index, coords in enumerate(coordinates):
        if (
            len(coords) < 2
            or any(len(c) != 3 or not all(math.isfinite(v) for v in c) for c in coords)
            or not parts[index].is_simple
            or coords[0] == coords[-1]
            or any(a == b for a, b in zip(coords, coords[1:], strict=False))
        ):
            raise ValueError("ambiguous_multipart_part")
        adjacency[coords[0]].append(index)
        adjacency[coords[-1]].append(index)
    ends = sorted(point for point, incident in adjacency.items() if len(incident) == 1)
    if len(ends) != 2 or any(len(incident) > 2 for incident in adjacency.values()):
        raise ValueError("branched_or_closed_multipart")
    current = ends[0]
    used: set[int] = set()
    ordered = []
    while True:
        available = [index for index in adjacency[current] if index not in used]
        if not available:
            break
        index = available[0]
        used.add(index)
        forward = coordinates[index][0] == current
        ordered.append((index, forward))
        current = coordinates[index][-1 if forward else 0]
    if len(used) != len(parts):
        raise ValueError("disjoint_multipart")
    if not next(forward for index, forward in ordered if index == 0):
        ordered = [(index, not forward) for index, forward in reversed(ordered)]
    result: list[Any] = []
    spans = []
    for index, forward in ordered:
        vertices = list(range(len(coordinates[index])))
        if not forward:
            vertices.reverse()
        coords = [coordinates[index][vertex] for vertex in vertices]
        result.extend(coords if not result else coords[1:])
        spans.extend(
            {"part_index": index, "start_vertex": a, "end_vertex": b}
            for a, b in zip(vertices, vertices[1:], strict=False)
        )
    if not LineString(result).is_simple:
        raise ValueError("ambiguous_multipart_chain")
    return result, spans
