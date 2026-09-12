"""Opt-in exact source-vertex noding; source geometry is never modified."""

import math
from collections import defaultdict
from typing import Any

import networkx as nx
from osgeo import ogr
from shapely import wkb
from shapely.geometry import LineString, MultiLineString

ENDPOINT_MODE = "endpoint-v1"
EXACT_MODE = "exact-shared-vertices-v1"
TOPOLOGY_MODES = (ENDPOINT_MODE, EXACT_MODE)


def reverse_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reverse traversal without changing the source's own vertex indexing."""
    return [
        dict(span, start_vertex=span["end_vertex"], end_vertex=span["start_vertex"])
        for span in reversed(spans)
    ]


def _span(fid: str, start: int, end: int) -> dict[str, Any]:
    return {"feature_id": fid, "part_index": 0, "start_vertex": start, "end_vertex": end}


def node_shared_vertices(
    graph: nx.MultiDiGraph,
    node_map: dict[Any, Any],
    node_attrs: dict[Any, Any],
    pathways: list[dict[str, Any]],
    transition_points: list[dict[str, Any]],
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Cut only existing same-level XYZ vertices shared by distinct source features.

    Endpoint snapping remains the legacy contract. Proposed new junctions whose
    grid cell also contains incompatible native identities are skipped, not merged.
    Multipart/self-loop exclusions remain explicit legacy limitations.
    """
    from wayfinding.etl.graph import round_half_up

    candidate = graph.copy()
    candidate.graph["topology_mode"] = EXACT_MODE
    audit: dict[str, Any] = {
        "version": "dt022-topology-audit-v1",
        "topology_mode": EXACT_MODE,
        "split_feature_count": 0,
        "junctions": [],
        "skipped_junctions": [],
        "metric_mismatches": [],
        "excluded_features": [],
        "features": [],
        "policy": "Exact level/XYZ source vertices; no proximity or interpolated intersections",
    }
    feature_edges: dict[str, list[Any]] = defaultdict(list)
    for u, v, key, data in candidate.edges(keys=True, data=True):
        if data.get("mode") == "pathway":
            feature_edges[str(data["feature_id"])].append((u, v, key))
    rows = {row["feature_id"]: row for row in pathways}
    owners: dict[Any, set[str]] = defaultdict(set)
    interiors: dict[Any, list[tuple[str, int]]] = defaultdict(list)
    cells: dict[Any, set[Any]] = defaultdict(set)

    def identity(level: str, coord: Any) -> tuple[Any, ...]:
        values = tuple(float(value) for value in coord)
        if len(values) != 3 or not all(math.isfinite(value) for value in values):
            raise ValueError("Topology requires finite XYZ source coordinates")
        return (level, *values)

    def cell(item: Any, order: int) -> tuple[float, float, int]:
        return (round_half_up(item[1], 2), round_half_up(item[2], 2), order)

    for fid, row in sorted(rows.items()):
        level = row["level_id"]
        order = node_map[("PW", fid, "start")][2]
        for role, coord in zip(("start", "end"), row["endpoints"], strict=True):
            item = identity(level, coord)
            cells[cell(item, order)].add(item)
            cells[node_map[("PW", fid, role)]].add(item)
        coords = row["coordinates"]
        if coords is None or fid not in feature_edges:
            audit["excluded_features"].append(
                {
                    "feature_id": fid,
                    "reason": "legacy_multipart" if coords is None else "legacy_excluded_self_loop",
                }
            )
            continue
        weight = row["length_3d"]
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (float, int))
            or not math.isfinite(weight)
            or weight <= 0
        ):
            raise ValueError(f"Invalid source metric for pathway {fid}")
        for index, coord in enumerate(coords):
            item = identity(level, coord)
            owners[item].add("PW:" + fid)
            cells[cell(item, order)].add(item)
            if 0 < index < len(coords) - 1:
                interiors[item].append((fid, index))
    for point in transition_points:
        item = identity(point["level_id"], point["coordinates"])
        owners[item].add("TR:" + point["feature_id"])
        cells[cell(item, point["vertical_order"])].add(item)
        cells[node_map[("TR", point["feature_id"], point["node_role"])]].add(item)

    proposed = {
        item: occurrences for item, occurrences in interiors.items() if len(owners[item]) > 1
    }
    for item, occurrences in proposed.items():
        order = node_map[("PW", occurrences[0][0], "start")][2]
        cells[cell(item, order)].add(item)
    cuts: dict[str, set[int]] = defaultdict(set)
    for item, occurrences in sorted(proposed.items()):
        order = node_map[("PW", occurrences[0][0], "start")][2]
        snapped = cell(item, order)
        record = {
            "level_id": item[0],
            "coordinates": list(item[1:]),
            "node": list(snapped),
            "owners": sorted(owners[item]),
        }
        if len(cells[snapped]) != 1:
            audit["skipped_junctions"].append({**record, "reason": "incompatible_snap_cell"})
            continue
        audit["junctions"].append(record)
        for fid, index in occurrences:
            cuts[fid].add(index)

    for fid, row in sorted(rows.items()):
        edges = feature_edges.get(fid, [])
        if not edges:
            continue
        coords = row["coordinates"]
        # Every candidate pathway preserves an explicit source identity, including
        # unchanged multipart geometry for which no complete span claim is made.
        for u, v, key in edges:
            data = candidate[u][v][key]
            spans = [_span(fid, 0, len(coords) - 1)] if coords else []
            if coords:
                data["geometry"] = LineString(coords[::-1] if key.endswith("_R") else coords)
            data.update(
                source_feature_id=fid,
                source_spans=reverse_spans(spans) if key.endswith("_R") else spans,
                source_spans_complete=coords is not None,
            )
        if not cuts[fid] or coords is None:
            continue
        indices = [0, *sorted(cuts[fid]), len(coords) - 1]
        order = node_map[("PW", fid, "start")][2]
        # Exact mode is additive: preserve every legacy endpoint node byte-for-byte.
        # Native WKB doubles at a half-centimetre boundary can otherwise round to
        # the adjacent cell compared with the legacy WKT endpoint path.
        nodes = [
            node_map[("PW", fid, "start")] if i == 0
            else node_map[("PW", fid, "end")] if i == len(coords) - 1
            else cell(identity(row["level_id"], coords[i]), order)
            for i in indices
        ]
        # Never discard nonzero source segments merely because endpoints quantize
        # together. Preserve this whole feature unchanged and disclose the skip.
        if any(a == b for a, b in zip(nodes, nodes[1:], strict=False)):
            audit["excluded_features"].append(
                {"feature_id": fid, "reason": "collapsed_split_piece"}
            )
            continue
        lengths = [
            math.fsum(math.dist(coords[i], coords[i + 1]) for i in range(start, end))
            for start, end in zip(indices, indices[1:], strict=False)
        ]
        native_length = math.fsum(lengths)
        if any(length <= 0 or not math.isfinite(length) for length in lengths):
            raise ValueError(f"Invalid native metric for pathway {fid}")
        weight = row["length_3d"]
        if abs(weight - native_length) > max(0.05, 0.005 * weight):
            audit["metric_mismatches"].append(
                {"feature_id": fid, "source_length_3d": weight, "native_length_3d": native_length}
            )
        weights = [weight * length / native_length for length in lengths]
        weights[-1] = weight - math.fsum(weights[:-1])
        if any(value <= 0 or not math.isfinite(value) for value in weights):
            raise ValueError(f"Invalid allocated metric for pathway {fid}")
        for edge in edges:
            candidate.remove_edge(*edge)
        pieces = []
        for start, end, u, v, allocated in zip(
            indices, indices[1:], nodes, nodes[1:], weights, strict=False
        ):
            physical_id = f"{fid}:v{start}-{end}"
            geometry = LineString(coords[start : end + 1])
            spans = [_span(fid, start, end)]
            data = {
                "feature_id": physical_id,
                "source_feature_id": fid,
                "level_id": row["level_id"],
                "mode": "pathway",
                "length_3d": allocated,
                "source_spans_complete": True,
            }
            candidate.add_edge(
                u, v, key="PW_" + physical_id, geometry=geometry, source_spans=spans, **data
            )
            candidate.add_edge(
                v,
                u,
                key="PW_" + physical_id + "_R",
                geometry=LineString(list(reversed(geometry.coords))),
                source_spans=reverse_spans(spans),
                **data,
            )
            pieces.append({"physical_id": physical_id, **spans[0], "length_3d": allocated})
        for index, node in zip(indices, nodes, strict=False):
            if node not in node_attrs:
                z = coords[index][2]
                node_attrs[node] = {
                    "x": node[0],
                    "y": node[1],
                    "vertical_order": node[2],
                    "level_ids": {row["level_id"]},
                    "z_min": z,
                    "z_max": z,
                    "z_mean": z,
                }
            candidate.nodes[node].update(node_attrs[node])
            if index in cuts[fid]:
                node_map[("PW", fid, f"vertex:{index}")] = node
        audit["split_feature_count"] += 1
        audit["features"].append(
            {
                "feature_id": fid,
                "source_length_3d": weight,
                "native_length_3d": native_length,
                "pieces": pieces,
            }
        )
    audit["new_node_count"] = len(set(candidate) - set(graph))
    audit["directed_edge_count_before"] = graph.number_of_edges()
    audit["directed_edge_count_after"] = candidate.number_of_edges()
    return candidate, audit


def apply_exact_noding(
    graph: nx.MultiDiGraph,
    gpkg_path: str,
    node_map: dict[Any, Any],
    node_attrs: dict[Any, Any],
    level_lookup: dict[str, int],
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Read normalized source copies; only candidate graph outputs are changed."""
    from wayfinding.etl.graph import extract_endpoints

    dataset = ogr.Open(gpkg_path, 0)
    pathways = []
    for feature in dataset.GetLayerByName("Pathways_26910"):
        geometry = wkb.loads(bytes(feature.GetGeometryRef().ExportToWkb()))
        if not isinstance(geometry, (LineString, MultiLineString)):
            raise ValueError("Unsupported pathway geometry for topology")
        coords = None
        if isinstance(geometry, LineString):
            coords = list(geometry.coords)
        elif isinstance(geometry, MultiLineString) and len(geometry.geoms) == 1:
            coords = list(geometry.geoms[0].coords)
        pathways.append(
            {
                "feature_id": str(feature.GetFID()),
                "level_id": feature.GetField("LEVEL_ID"),
                "coordinates": coords,
                "endpoints": extract_endpoints(geometry),
                "length_3d": feature.GetField("LENGTH_3D"),
            }
        )
    transitions = []
    for feature in dataset.GetLayerByName("Transitions_26910"):
        geometry = wkb.loads(bytes(feature.GetGeometryRef().ExportToWkb()))
        if not isinstance(geometry, (LineString, MultiLineString)):
            raise ValueError("Unsupported transition geometry for topology")
        for role, coord in zip(("FROM", "TO"), extract_endpoints(geometry), strict=False):
            level_id = f"{feature.GetField('FACILITY_ID')}_{feature.GetField('LEVEL_NAME_' + role)}"
            transitions.append(
                {
                    "feature_id": str(feature.GetFID()),
                    "level_id": level_id,
                    "coordinates": coord,
                    "vertical_order": level_lookup[level_id],
                    "node_role": "start" if role == "FROM" else "end",
                }
            )
    dataset = None
    return node_shared_vertices(graph, node_map, node_attrs, pathways, transitions)
