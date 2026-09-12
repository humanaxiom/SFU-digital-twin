"""Graph construction from snapped pathway and transition endpoints.

This module implements DT-005: Graph Node Snapping and Raw Graph Construction.
It creates a NetworkX MultiDiGraph with bidirectional pathway edges, snapping all
endpoints to a 1 cm grid in EPSG:26910 coordinates.

Node identity: (x, y, vertical_order) tuples where x, y are rounded to 2 decimal places
using round-half-up quantization, and vertical_order comes from the level_26910 table.

Edge keys follow convention:
- Forward: "PW_{feature_id}" for pathways
- Reverse: "PW_{feature_id}_R"
"""

import hashlib
import json
import logging
import random
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from math import floor
from pathlib import Path
from typing import Any, cast

import networkx as nx
from osgeo import ogr  # pyright: ignore[reportMissingImports]
from shapely import wkt
from shapely.geometry import LineString, MultiLineString, Point

from wayfinding.etl.topology import ENDPOINT_MODE, EXACT_MODE, TOPOLOGY_MODES, reverse_spans

logger = logging.getLogger(__name__)
ogr.UseExceptions()


# Type aliases for clarity
Coordinate = tuple[float, float, float]  # (x, y, z)
NodeID = tuple[float, float, int]  # (x, y, vertical_order)
NodeMapKey = tuple[str, str, str]  # (layer_prefix, feature_id, endpoint_role)


def round_half_up(value: float, decimals: int) -> float:
    """Round a float to n decimal places using round-half-up (not banker's rounding).

    Args:
        value: The value to round
        decimals: Number of decimal places

    Returns:
        Rounded value

    Example:
        >>> round_half_up(505123.455, 2)
        505123.46
        >>> round_half_up(505123.445, 2)
        505123.45
    """
    multiplier = 10**decimals
    return floor(value * multiplier + 0.5) / multiplier


def extract_endpoints(
    geometry: LineString | MultiLineString,
) -> tuple[Coordinate, Coordinate]:
    """Extract start and end coordinates from a MultiLineString Z geometry.

    For multipart geometries:
    - Start: first coordinate of first part
    - End: last coordinate of last part

    Args:
        geometry: Shapely MultiLineString (may be single-part)

    Returns:
        (start_coord, end_coord) each as (x, y, z) tuple
    """
    if isinstance(geometry, LineString):
        # Wrap single LineString as MultiLineString for uniform handling
        geometry = MultiLineString([geometry])

    first_part = geometry.geoms[0]
    last_part = geometry.geoms[-1]

    start = first_part.coords[0]
    end = last_part.coords[-1]
    start_coord: Coordinate = (float(start[0]), float(start[1]), float(start[2]))
    end_coord: Coordinate = (float(end[0]), float(end[1]), float(end[2]))

    return start_coord, end_coord


def load_level_lookup(gpkg_path: str) -> dict[str, int]:
    """Load level_id -> vertical_order mapping from level_26910 table.

    Args:
        gpkg_path: Path to GeoPackage with level_26910 table

    Returns:
        dict mapping level_id (str) to vertical_order (int)

    Raises:
        RuntimeError: If layer not found or cannot be read
    """
    ds = ogr.Open(gpkg_path, 0)  # 0 = read-only
    if ds is None:
        raise RuntimeError(f"Cannot open GeoPackage: {gpkg_path}")

    layer = ds.GetLayerByName("level_26910")
    if layer is None:
        raise RuntimeError(f"Layer 'level_26910' not found in {gpkg_path}")

    level_lookup = {}
    for feature in layer:
        level_id = feature.GetField("level_id")
        vertical_order = feature.GetField("vertical_order")

        if level_id is None or vertical_order is None:
            logger.warning(f"Skipping feature with null level_id or vertical_order: {feature}")
            continue

        level_lookup[level_id] = vertical_order

    ds = None  # Close dataset

    if not level_lookup:
        raise RuntimeError("No valid level mappings found in level_26910 table")

    logger.info(f"Loaded {len(level_lookup)} level mappings: {sorted(level_lookup.items())}")
    return level_lookup


def snap_nodes(
    gpkg_path: str,
    level_lookup: dict[str, int],
) -> tuple[dict[NodeMapKey, NodeID], dict[NodeID, dict[str, Any]]]:
    """Snap all pathway and transition endpoints to 1 cm grid.

    Reads Pathways_26910 and Transitions_26910 layers, extracts endpoints,
    rounds x,y to 2 decimal places (1 cm in EPSG:26910), looks up vertical_order
    from level_lookup, and builds:
    - node_map: maps (layer_prefix, fid, endpoint_role) -> (x, y, vertical_order)
    - node_attrs: maps snapped node IDs to coordinate, level, and Z summary attributes

    Args:
        gpkg_path: Path to GeoPackage
        level_lookup: dict[level_id] -> vertical_order

    Returns:
        (node_map, node_attrs) tuple
    """
    node_map: dict[NodeMapKey, NodeID] = {}
    raw_node_data: dict[NodeID, list[tuple[str, float]]] = defaultdict(list)

    ds = ogr.Open(gpkg_path, 0)
    if ds is None:
        raise RuntimeError(f"Cannot open GeoPackage: {gpkg_path}")

    # Process Pathways_26910
    pathways_layer = ds.GetLayerByName("Pathways_26910")
    if pathways_layer is None:
        raise RuntimeError("Pathways_26910 layer not found")

    pathways_layer.ResetReading()
    for feature in pathways_layer:
        fid = str(feature.GetFID())
        level_id = feature.GetField("LEVEL_ID")

        if level_id not in level_lookup:
            raise ValueError(
                f"Pathway FID {fid} has LEVEL_ID '{level_id}' not in level_lookup. "
                f"Available levels: {sorted(level_lookup.keys())}"
            )

        vertical_order = level_lookup[level_id]
        geom_ogr = feature.GetGeometryRef()
        geom_wkt_str = geom_ogr.ExportToWkt()
        geom = wkt.loads(geom_wkt_str)
        if not isinstance(geom, (LineString, MultiLineString)):
            raise ValueError(f"Pathway FID {fid} has unsupported geometry {geom.geom_type}")

        start_coord, end_coord = extract_endpoints(geom)

        # Snap to 1 cm grid
        start_node = (
            round_half_up(start_coord[0], 2),
            round_half_up(start_coord[1], 2),
            vertical_order,
        )
        end_node = (
            round_half_up(end_coord[0], 2),
            round_half_up(end_coord[1], 2),
            vertical_order,
        )

        # Record in node_map with layer-prefixed keys
        node_map[("PW", fid, "start")] = start_node
        node_map[("PW", fid, "end")] = end_node

        # Collect raw data for node attributes (level_id and Z coordinate)
        raw_node_data[start_node].append((level_id, start_coord[2]))
        raw_node_data[end_node].append((level_id, end_coord[2]))

    logger.info(f"Snapped {len(list(pathways_layer))} pathway endpoints")

    # Process Transitions_26910
    transitions_layer = ds.GetLayerByName("Transitions_26910")
    if transitions_layer is None:
        raise RuntimeError("Transitions_26910 layer not found")

    transitions_layer.ResetReading()
    for feature in transitions_layer:
        fid = str(feature.GetFID())
        facility_id = feature.GetField("FACILITY_ID")
        level_name_from = feature.GetField("LEVEL_NAME_FROM")
        level_name_to = feature.GetField("LEVEL_NAME_TO")

        # Construct level_id from facility_id + level_name
        level_id_from = f"{facility_id}_{level_name_from}"
        level_id_to = f"{facility_id}_{level_name_to}"

        if level_id_from not in level_lookup:
            raise ValueError(
                f"Transition FID {fid} has LEVEL_ID_FROM '{level_id_from}' not in level_lookup"
            )
        if level_id_to not in level_lookup:
            raise ValueError(
                f"Transition FID {fid} has LEVEL_ID_TO '{level_id_to}' not in level_lookup"
            )

        vertical_order_from = level_lookup[level_id_from]
        vertical_order_to = level_lookup[level_id_to]

        geom_ogr = feature.GetGeometryRef()
        geom_wkt_str = geom_ogr.ExportToWkt()
        geom = wkt.loads(geom_wkt_str)
        if not isinstance(geom, (LineString, MultiLineString)):
            raise ValueError(f"Transition FID {fid} has unsupported geometry {geom.geom_type}")

        start_coord, end_coord = extract_endpoints(geom)

        # Snap to 1 cm grid - start uses FROM vertical_order, end uses TO vertical_order
        start_node = (
            round_half_up(start_coord[0], 2),
            round_half_up(start_coord[1], 2),
            vertical_order_from,
        )
        end_node = (
            round_half_up(end_coord[0], 2),
            round_half_up(end_coord[1], 2),
            vertical_order_to,
        )

        # Record in node_map with TR prefix
        node_map[("TR", fid, "start")] = start_node
        node_map[("TR", fid, "end")] = end_node

        # Collect raw data for node attributes
        raw_node_data[start_node].append((level_id_from, start_coord[2]))
        raw_node_data[end_node].append((level_id_to, end_coord[2]))

    logger.info(f"Snapped {len(list(transitions_layer))} transition endpoints")

    ds = None  # Close dataset

    # Build node attributes from raw data
    node_attrs: dict[NodeID, dict[str, Any]] = {}
    for node_id, level_z_pairs in raw_node_data.items():
        level_ids = {level_id for level_id, z in level_z_pairs}
        z_values = [z for level_id, z in level_z_pairs]

        node_attrs[node_id] = {
            "x": node_id[0],
            "y": node_id[1],
            "vertical_order": node_id[2],
            "level_ids": level_ids,
            "z_min": min(z_values),
            "z_max": max(z_values),
            "z_mean": sum(z_values) / len(z_values),
        }

    logger.info(
        f"Snapped {len(node_map)} total endpoints to {len(node_attrs)} unique nodes"
    )
    return node_map, node_attrs


def build_raw_graph(
    gpkg_path: str,
    node_map: dict[NodeMapKey, NodeID],
    node_attrs: dict[NodeID, dict[str, Any]],
    level_lookup: dict[str, int],
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Build NetworkX MultiDiGraph with bidirectional pathway edges.

    Reads Pathways_26910 layer, creates two directed edges per pathway feature
    (forward and reverse), each with 5 attributes: length_3d, mode, level_id,
    feature_id, geometry.

    Self-loops (start_node == end_node after snapping) are detected, logged,
    and excluded.

    Args:
        gpkg_path: Path to GeoPackage
        node_map: Mapping from (layer_prefix, fid, role) to snapped node ID
        node_attrs: Node attributes dict
        level_lookup: Level ID to vertical_order mapping (for stats)

    Returns:
        (G, stats) where G is nx.MultiDiGraph and stats is a dict with:
        - etl_version, timestamp
        - node_count, edge_count, mean_degree
        - self_loops_removed, self_loop_fids
        - connectivity_by_level
        - z_range_by_level
    """
    graph = nx.MultiDiGraph()

    # Don't pre-populate nodes - they'll be added automatically by add_edge()
    # This ensures no isolated nodes from self-loops that were excluded

    ds = ogr.Open(gpkg_path, 0)
    if ds is None:
        raise RuntimeError(f"Cannot open GeoPackage: {gpkg_path}")

    pathways_layer = ds.GetLayerByName("Pathways_26910")
    if pathways_layer is None:
        raise RuntimeError("Pathways_26910 layer not found")

    self_loops_removed = 0
    self_loop_fids = []

    pathways_layer.ResetReading()
    for feature in pathways_layer:
        fid = str(feature.GetFID())
        level_id = feature.GetField("LEVEL_ID")
        length_3d = feature.GetField("LENGTH_3D")

        # Look up snapped nodes
        start_node = node_map[("PW", fid, "start")]
        end_node = node_map[("PW", fid, "end")]

        # Detect self-loops
        if start_node == end_node:
            logger.warning(
                f"Self-loop detected: Pathway FID {fid}, level {level_id}, "
                f"snapped to {start_node}. Excluding from graph."
            )
            self_loops_removed += 1
            self_loop_fids.append(fid)
            continue

        # Get geometry as Shapely LineString
        geom_ogr = feature.GetGeometryRef()
        geom_wkt_str = geom_ogr.ExportToWkt()
        source_geom = wkt.loads(geom_wkt_str)
        if not isinstance(source_geom, (LineString, MultiLineString)):
            raise ValueError(
                f"Pathway FID {fid} has unsupported geometry {source_geom.geom_type}"
            )

        # Convert to single LineString if it's a simple single-part multilinestring
        if isinstance(source_geom, LineString):
            geom = source_geom
        elif len(source_geom.geoms) == 1:
            geom = cast(LineString, source_geom.geoms[0])
        else:
            # Flatten multipart into single LineString by concatenating coordinates
            all_coords = []
            for part in source_geom.geoms:
                all_coords.extend(part.coords)
            geom = LineString(all_coords)

        # Create forward edge (this adds nodes automatically if they don't exist)
        forward_key = f"PW_{fid}"
        graph.add_edge(
            start_node,
            end_node,
            key=forward_key,
            length_3d=length_3d,
            mode="pathway",
            level_id=level_id,
            feature_id=fid,
            geometry=geom,
        )

        # Set node attributes (nodes were created by add_edge above)
        if start_node in node_attrs:
            graph.nodes[start_node].update(node_attrs[start_node])
        if end_node in node_attrs:
            graph.nodes[end_node].update(node_attrs[end_node])

        # Create reverse edge with reversed geometry
        reverse_key = f"PW_{fid}_R"
        reverse_geom = LineString(list(reversed(geom.coords)))
        graph.add_edge(
            end_node,
            start_node,
            key=reverse_key,
            length_3d=length_3d,
            mode="pathway",
            level_id=level_id,
            feature_id=fid,
            geometry=reverse_geom,
        )

    ds = None  # Close dataset

    logger.info(
        f"Built graph with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges "
        f"({self_loops_removed} self-loops removed)"
    )

    # Compute statistics
    stats = compute_graph_stats(
        graph, level_lookup, self_loops_removed, self_loop_fids
    )

    return graph, stats


def compute_graph_stats(
    graph: nx.MultiDiGraph,
    level_lookup: dict[str, int],
    self_loops_removed: int,
    self_loop_fids: list[str],
) -> dict[str, Any]:
    """Compute graph statistics for graph_raw_stats.json.

    Args:
        graph: NetworkX MultiDiGraph
        level_lookup: Level ID to vertical_order mapping
        self_loops_removed: Count of self-loops excluded
        self_loop_fids: List of FIDs that were self-loops

    Returns:
        Statistics dict
    """
    # Basic counts
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()

    # Mean degree (total degree / node count)
    degrees = dict(graph.degree())
    mean_degree = sum(degrees.values()) / node_count if node_count > 0 else 0.0

    # Connectivity by level
    connectivity_by_level = {}
    for level_id in sorted(level_lookup):
        level_nodes = {
            node
            for start, end, data in graph.edges(data=True)
            if data["level_id"] == level_id
            for node in (start, end)
        }

        if not level_nodes:
            connectivity_by_level[level_id] = {
                "node_count": 0,
                "component_count": 0,
            }
            continue

        # Create subgraph for this level
        subgraph = nx.Graph()
        subgraph.add_edges_from(
            (start, end)
            for start, end, data in graph.edges(data=True)
            if data["level_id"] == level_id
        )
        component_count = nx.number_connected_components(subgraph)
        largest_component_size = max(
            (len(component) for component in nx.connected_components(subgraph)),
            default=0,
        )

        connectivity_by_level[level_id] = {
            "node_count": len(level_nodes),
            "component_count": component_count,
            "largest_component_size": largest_component_size,
        }

    # Z range by level
    z_range_by_level = {}
    for level_id in sorted(level_lookup):
        level_nodes = {
            node
            for start, end, data in graph.edges(data=True)
            if data["level_id"] == level_id
            for node in (start, end)
        }

        if not level_nodes:
            z_range_by_level[level_id] = {"z_min": None, "z_max": None, "z_mean": None}
            continue

        z_mins = [graph.nodes[node]["z_min"] for node in level_nodes]
        z_maxs = [graph.nodes[node]["z_max"] for node in level_nodes]
        z_means = [graph.nodes[node]["z_mean"] for node in level_nodes]

        z_range_by_level[level_id] = {
            "z_min": min(z_mins),
            "z_max": max(z_maxs),
            "z_mean": sum(z_means) / len(z_means),
        }

    stats = {
        "etl_version": "0.1.0",
        "timestamp": datetime.now().astimezone().isoformat(),
        "node_count": node_count,
        "edge_count": edge_count,
        "mean_degree": round(mean_degree, 2),
        "self_loops_removed": self_loops_removed,
        "self_loop_fids": self_loop_fids,
        "connectivity_by_level": connectivity_by_level,
        "z_range_by_level": z_range_by_level,
    }

    return stats


def run_graph_raw(output_dir: Path, *, topology_mode: str = ENDPOINT_MODE) -> int:
    """Run graph-raw ETL step: snap nodes and build raw pathway graph.

    Outputs:
    - graph_raw.pkl: Pickled NetworkX MultiDiGraph
    - node_map.pkl: Pickled node_map for DT-006
    - graph_raw_stats.json: Graph statistics

    Args:
        output_dir: Directory for output artifacts (typically /workspace/build)

    Returns:
        Exit code (0 = success)
    """
    import pickle

    if topology_mode not in TOPOLOGY_MODES:
        raise ValueError("Unsupported topology mode")

    gpkg_path = output_dir / "wayfinding.gpkg"

    if not gpkg_path.exists():
        logger.error(f"GeoPackage not found: {gpkg_path}")
        logger.error("Run 'make etl-extract' and 'make etl-normalise' first.")
        return 1

    logger.info("=== DT-005: Graph Node Snapping and Raw Graph Construction ===")
    logger.info(f"Input: {gpkg_path}")

    # Step 1: Load level lookup
    logger.info("Step 1/3: Loading level lookup from level_26910 table...")
    level_lookup = load_level_lookup(str(gpkg_path))

    # Step 2: Snap nodes
    logger.info("Step 2/3: Snapping pathway and transition endpoints to 1 cm grid...")
    node_map, node_attrs = snap_nodes(str(gpkg_path), level_lookup)

    # Step 3: Build graph
    logger.info("Step 3/3: Building raw pathway graph (bidirectional edges)...")
    graph, stats = build_raw_graph(
        str(gpkg_path), node_map, node_attrs, level_lookup
    )

    if topology_mode == EXACT_MODE:
        from wayfinding.etl.topology import apply_exact_noding

        graph, audit = apply_exact_noding(
            graph, str(gpkg_path), node_map, node_attrs, level_lookup
        )
        stats = compute_graph_stats(graph, level_lookup, stats["self_loops_removed"],
                                    stats["self_loop_fids"])
        stats["topology_mode"] = topology_mode
        with (output_dir / "topology_audit.json").open("x", encoding="utf-8") as stream:
            json.dump(audit, stream, indent=2, sort_keys=True, allow_nan=False)

    # Serialize outputs
    graph_raw_pkl = output_dir / "graph_raw.pkl"
    node_map_pkl = output_dir / "node_map.pkl"
    stats_json = output_dir / "graph_raw_stats.json"

    logger.info(f"Writing graph to {graph_raw_pkl}...")
    with open(graph_raw_pkl, "wb") as f:
        pickle.dump(graph, f, protocol=5)

    logger.info(f"Writing node_map to {node_map_pkl}...")
    with open(node_map_pkl, "wb") as f:
        pickle.dump(node_map, f, protocol=5)

    logger.info(f"Writing stats to {stats_json}...")
    with open(stats_json, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("\n=== Graph Construction Complete ===")
    logger.info(f"Nodes: {stats['node_count']:,}")
    logger.info(f"Edges: {stats['edge_count']:,}")
    logger.info(f"Mean degree: {stats['mean_degree']:.2f}")
    logger.info(f"Self-loops removed: {stats['self_loops_removed']}")
    logger.info("\nOutputs:")
    logger.info(f"  {graph_raw_pkl}")
    logger.info(f"  {node_map_pkl}")
    logger.info(f"  {stats_json}")

    return 0


def add_transitions(
    graph: nx.MultiDiGraph,
    node_map: dict[NodeMapKey, NodeID],
    gpkg_path: str,
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Add transition edges (stairs, elevators) to pathway graph.

    Reads Transitions_26910 layer from GeoPackage, looks up snapped endpoints
    in node_map, and adds bidirectional edges. Marks all transition endpoints
    as protected from contraction. Adds transition-only nodes not present in
    the pathway graph with complete node attributes.

    Args:
        graph: NetworkX MultiDiGraph with pathway edges (from DT-005)
        node_map: Mapping from (layer_prefix, fid, role) to snapped node ID
        gpkg_path: Path to GeoPackage with Transitions_26910 layer

    Returns:
        (graph, stats) tuple where:
        - graph is the updated MultiDiGraph with transition edges added
        - stats is a dict with transition counts, connectivity, warnings

    Raises:
        ValueError: If any transition endpoint not found in node_map (orphan)
        RuntimeError: If connectivity regresses or no components bridged
    """
    ds = ogr.Open(gpkg_path, 0)  # Read-only
    if ds is None:
        raise RuntimeError(f"Cannot open GeoPackage: {gpkg_path}")

    transitions_layer = ds.GetLayerByName("Transitions_26910")
    if transitions_layer is None:
        raise RuntimeError("Transitions_26910 layer not found")

    pathway_graph = nx.Graph()
    pathway_graph.add_edges_from(
        (start, end)
        for start, end, edge_data in graph.edges(data=True)
        if edge_data.get("mode") == "pathway"
    )
    pathway_only_baseline = nx.number_connected_components(pathway_graph)

    # Transition type mapping per data findings and ADR-0004
    transition_type_map = {
        2: "stairs",
        4: "elevator",
    }

    # Track statistics
    transition_features = 0
    stairs_arcs = 0
    elevator_arcs = 0
    express_elevators = []
    orphan_transitions = []
    transition_endpoint_nodes = set()

    # Collect raw node data for transition-only nodes
    raw_node_data: dict[NodeID, list[tuple[str, float]]] = defaultdict(list)

    # First pass: validate all endpoints exist and collect data
    transitions_layer.ResetReading()
    transition_data = []

    for feature in transitions_layer:
        fid = str(feature.GetFID())
        transition_type = feature.GetField("TRANSITION_TYPE")
        facility_id = feature.GetField("FACILITY_ID")
        level_name_from = feature.GetField("LEVEL_NAME_FROM")
        level_name_to = feature.GetField("LEVEL_NAME_TO")
        length_3d = feature.GetField("LENGTH_3D")

        if transition_type not in transition_type_map:
            raise ValueError(
                f"Transition FID {fid} has unsupported TRANSITION_TYPE {transition_type}"
            )

        mode = transition_type_map[transition_type]
        level_id_from = f"{facility_id}_{level_name_from}"
        level_id_to = f"{facility_id}_{level_name_to}"

        # Look up snapped endpoints in node_map
        start_key = ("TR", fid, "start")
        end_key = ("TR", fid, "end")

        if start_key not in node_map:
            orphan_transitions.append((fid, "start", level_id_from))
            continue

        if end_key not in node_map:
            orphan_transitions.append((fid, "end", level_id_to))
            continue

        start_node = node_map[start_key]
        end_node = node_map[end_key]

        # Extract vertical_order from node IDs (third element)
        vertical_order_from = start_node[2]
        vertical_order_to = end_node[2]

        # Get geometry
        geom_ogr = feature.GetGeometryRef()
        geom_wkt_str = geom_ogr.ExportToWkt()
        geom = wkt.loads(geom_wkt_str)

        if not isinstance(geom, (LineString, MultiLineString)):
            raise ValueError(f"Transition FID {fid} has unsupported geometry {geom.geom_type}")

        # Convert to LineString
        if isinstance(geom, LineString):
            line_geom = geom
        elif len(geom.geoms) == 1:
            line_geom = cast(LineString, geom.geoms[0])
        else:
            # Flatten multipart into single LineString
            all_coords = []
            for part in geom.geoms:
                all_coords.extend(part.coords)
            line_geom = LineString(all_coords)

        # Collect endpoint Z coordinates for node attributes
        start_coord, end_coord = extract_endpoints(geom)
        raw_node_data[start_node].append((level_id_from, start_coord[2]))
        raw_node_data[end_node].append((level_id_to, end_coord[2]))

        # Track express elevators (vertical_order delta > 1)
        vo_delta = abs(vertical_order_to - vertical_order_from)
        if mode == "elevator" and vo_delta > 1:
            express_elevators.append({
                "feature_id": fid,
                "vertical_order_from": vertical_order_from,
                "vertical_order_to": vertical_order_to,
            })

        transition_data.append({
            "fid": fid,
            "mode": mode,
            "start_node": start_node,
            "end_node": end_node,
            "level_id_from": level_id_from,
            "level_id_to": level_id_to,
            "vertical_order_from": vertical_order_from,
            "vertical_order_to": vertical_order_to,
            "length_3d": length_3d,
            "geometry": line_geom,
        })

        transition_endpoint_nodes.add(start_node)
        transition_endpoint_nodes.add(end_node)
        transition_features += 1

    ds = None  # Close dataset

    # Fail on orphan transitions
    if orphan_transitions:
        orphan_details = ", ".join(
            f"FID {fid} {endpoint} ({level_id})"
            for fid, endpoint, level_id in orphan_transitions[:5]
        )
        raise ValueError(
            f"Found {len(orphan_transitions)} orphan transition(s) with endpoints "
            f"not in node_map: {orphan_details}. This indicates a DT-005 snapping bug."
        )

    logger.info(f"Validated {transition_features} transition features, all endpoints in node_map")

    # Add transition-only nodes (not in graph yet) with complete node attributes
    transition_only_nodes = transition_endpoint_nodes - set(graph.nodes())

    for node_id in transition_only_nodes:
        if node_id in raw_node_data:
            level_z_pairs = raw_node_data[node_id]
            level_ids = {level_id for level_id, z in level_z_pairs}
            z_values = [z for level_id, z in level_z_pairs]

            # Add node with complete DT-005 attribute contract
            graph.add_node(
                node_id,
                x=node_id[0],
                y=node_id[1],
                vertical_order=node_id[2],
                level_ids=level_ids,
                z_min=min(z_values),
                z_max=max(z_values),
                z_mean=sum(z_values) / len(z_values),
            )

    logger.info(
        f"Added {len(transition_only_nodes)} transition-only nodes with complete attributes"
    )

    # Add transition edges (bidirectional)
    for trans in transition_data:
        # Forward edge
        forward_key = f"TR_{trans['fid']}"
        graph.add_edge(
            trans["start_node"],
            trans["end_node"],
            key=forward_key,
            length_3d=trans["length_3d"],
            mode=trans["mode"],
            level_id_from=trans["level_id_from"],
            level_id_to=trans["level_id_to"],
            vertical_order_from=trans["vertical_order_from"],
            vertical_order_to=trans["vertical_order_to"],
            feature_id=trans["fid"],
            geometry=trans["geometry"],
        )

        # Reverse edge with reversed geometry
        reverse_key = f"TR_{trans['fid']}_R"
        reverse_geom = LineString(list(reversed(trans["geometry"].coords)))
        graph.add_edge(
            trans["end_node"],
            trans["start_node"],
            key=reverse_key,
            length_3d=trans["length_3d"],
            mode=trans["mode"],
            level_id_from=trans["level_id_to"],
            level_id_to=trans["level_id_from"],
            vertical_order_from=trans["vertical_order_to"],
            vertical_order_to=trans["vertical_order_from"],
            feature_id=trans["fid"],
            geometry=reverse_geom,
        )

        if trans["mode"] == "stairs":
            stairs_arcs += 2
        elif trans["mode"] == "elevator":
            elevator_arcs += 2

    logger.info(
        f"Added {transition_features * 2} transition edges "
        f"({stairs_arcs} stairs, {elevator_arcs} elevator)"
    )

    # Mark all transition endpoints as protected
    for node in transition_endpoint_nodes:
        graph.nodes[node]["is_transition_endpoint"] = True

    logger.info(f"Marked {len(transition_endpoint_nodes)} transition endpoints as protected")

    # Compute connectivity statistics
    pathway_arcs = sum(
        1 for u, v, k, d in graph.edges(keys=True, data=True) if d["mode"] == "pathway"
    )

    # Default profile: pathway + stairs + elevator
    default_graph = nx.Graph()
    for u, v, _k, d in graph.edges(keys=True, data=True):
        if d["mode"] in ("pathway", "stairs", "elevator"):
            default_graph.add_edge(u, v)

    default_components = list(nx.connected_components(default_graph))
    default_component_count = len(default_components)
    default_largest = max((len(c) for c in default_components), default=0)
    default_component_sizes = sorted((len(c) for c in default_components), reverse=True)

    # Accessible profile: pathway + elevator only
    accessible_graph = nx.Graph()
    for u, v, _k, d in graph.edges(keys=True, data=True):
        if d["mode"] in ("pathway", "elevator"):
            accessible_graph.add_edge(u, v)

    accessible_components = list(nx.connected_components(accessible_graph))
    accessible_component_count = len(accessible_components)
    accessible_largest = max((len(c) for c in accessible_components), default=0)
    accessible_component_sizes = sorted((len(c) for c in accessible_components), reverse=True)

    default_bridged = pathway_only_baseline - default_component_count
    accessible_bridged = pathway_only_baseline - accessible_component_count
    stairs_bridged = default_bridged - accessible_bridged

    # Validate non-regression
    if default_component_count > pathway_only_baseline:
        raise RuntimeError(
            f"Default profile component count ({default_component_count}) increased from "
            f"pathway-only baseline ({pathway_only_baseline}). This indicates a node-identity bug."
        )

    if default_bridged <= 0:
        raise RuntimeError(
            f"Default profile bridged zero components. This suggests transitions not connecting "
            f"across components (pathway baseline: {pathway_only_baseline}, "
            f"current: {default_component_count})."
        )

    if accessible_component_count > pathway_only_baseline:
        raise RuntimeError(
            f"Accessible profile component count ({accessible_component_count}) increased from "
            f"pathway-only baseline ({pathway_only_baseline}). This indicates a bug."
        )

    if accessible_bridged <= 0:
        raise RuntimeError(
            "Accessible profile bridged zero components. This suggests elevators not connecting "
            "across components."
        )

    if stairs_bridged <= 0:
        raise RuntimeError(
            "Default profile gained no additional component bridges from stairs. "
            "This suggests stairs are not connecting across components."
        )

    logger.info(
        f"Default profile: {default_component_count} components "
        f"(baseline: {pathway_only_baseline}, bridged: {default_bridged}), "
        f"largest: {default_largest}"
    )

    logger.info(
        f"Accessible profile: {accessible_component_count} components "
        f"(baseline: {pathway_only_baseline}, bridged: {accessible_bridged}), "
        f"largest: {accessible_largest}"
    )

    # Emit warning for accessible profile fragmentation
    warning_msg = (
        f"Accessible profile has {accessible_component_count} connected components; "
        f"elevator-only routing available within connected regions only. Stairs excluded "
        f"from accessible profile. Fragmentation due to pathway topology gaps "
        f"(gap G2, thin elevator coverage). No wheelchair certification implied "
        f"(elevator-only != wheelchair-accessible). Query-time 'no route available' errors "
        f"expected for disconnected unit pairs. Not verified: door_width, path_width, slope, "
        f"powered_doors, surface. See ADR-0005."
    )

    logger.warning(warning_msg)

    # Build stats dict
    stats = {
        "etl_version": "0.1.0",
        "timestamp": datetime.now().astimezone().isoformat(),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "mean_degree": round(
            sum(dict(graph.degree()).values()) / graph.number_of_nodes()
            if graph.number_of_nodes() > 0
            else 0.0,
            2,
        ),
        "pathway_arcs": pathway_arcs,
        "stairs_arcs": stairs_arcs,
        "elevator_arcs": elevator_arcs,
        "transition_features_processed": transition_features,
        "express_elevators": express_elevators,
        "protected_nodes": len(transition_endpoint_nodes),
        "connectivity_default_profile": {
            "component_count": default_component_count,
            "largest_component_size": default_largest,
            "pathway_only_baseline": pathway_only_baseline,
            "components_bridged_by_transitions": default_bridged,
            "components_bridged_by_stairs": stairs_bridged,
            "component_sizes": default_component_sizes,
        },
        "connectivity_accessible_profile": {
            "component_count": accessible_component_count,
            "largest_component_size": accessible_largest,
            "pathway_only_baseline": pathway_only_baseline,
            "components_bridged_by_elevators": accessible_bridged,
            "component_sizes": accessible_component_sizes,
        },
        "warnings": [warning_msg],
    }

    return graph, stats


def run_graph_transitions(output_dir: Path) -> int:
    """Run graph-transitions ETL step: add transition edges to pathway graph.

    Loads graph_raw.pkl and node_map.pkl from DT-005, adds transition edges,
    and outputs graph_with_transitions.pkl and graph_with_transitions_stats.json.

    Args:
        output_dir: Directory for output artifacts (typically /workspace/build)

    Returns:
        Exit code (0 = success)
    """
    import pickle

    graph_raw_pkl = output_dir / "graph_raw.pkl"
    node_map_pkl = output_dir / "node_map.pkl"
    gpkg_path = output_dir / "wayfinding.gpkg"

    # Validate inputs exist
    if not graph_raw_pkl.exists():
        logger.error(f"graph_raw.pkl not found: {graph_raw_pkl}")
        logger.error("Run 'make etl-graph-raw' first.")
        return 1

    if not node_map_pkl.exists():
        logger.error(f"node_map.pkl not found: {node_map_pkl}")
        logger.error("Run 'make etl-graph-raw' first.")
        return 1

    if not gpkg_path.exists():
        logger.error(f"GeoPackage not found: {gpkg_path}")
        logger.error("Run 'make etl-extract' and 'make etl-normalise' first.")
        return 1

    logger.info("=== DT-006: Add Transition Edges to Graph ===")
    logger.info(f"Inputs: {graph_raw_pkl}, {node_map_pkl}, {gpkg_path}")

    # Load inputs
    logger.info("Loading graph_raw.pkl...")
    with open(graph_raw_pkl, "rb") as f:
        graph = pickle.load(f)

    logger.info("Loading node_map.pkl...")
    with open(node_map_pkl, "rb") as f:
        node_map = pickle.load(f)

    # Add transitions
    logger.info("Adding transition edges...")
    graph, stats = add_transitions(graph, node_map, str(gpkg_path))

    # Serialize outputs
    graph_transitions_pkl = output_dir / "graph_with_transitions.pkl"
    stats_json = output_dir / "graph_with_transitions_stats.json"

    logger.info(f"Writing graph to {graph_transitions_pkl}...")
    with open(graph_transitions_pkl, "wb") as f:
        pickle.dump(graph, f, protocol=5)

    logger.info(f"Writing stats to {stats_json}...")
    with open(stats_json, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("\n=== Graph with Transitions Complete ===")
    logger.info(f"Nodes: {stats['node_count']:,}")
    logger.info(f"Edges: {stats['edge_count']:,}")
    logger.info(f"  Pathway: {stats['pathway_arcs']:,}")
    logger.info(f"  Stairs: {stats['stairs_arcs']:,}")
    logger.info(f"  Elevator: {stats['elevator_arcs']:,}")
    logger.info(f"Mean degree: {stats['mean_degree']:.2f}")
    logger.info(f"Protected transition endpoints: {stats['protected_nodes']}")
    logger.info(f"Express elevators: {len(stats['express_elevators'])}")
    logger.info(
        f"\nDefault profile connectivity: "
        f"{stats['connectivity_default_profile']['component_count']} components "
        f"(bridged {stats['connectivity_default_profile']['components_bridged_by_transitions']} "
        f"from {stats['connectivity_default_profile']['pathway_only_baseline']} baseline)"
    )
    logger.info(
        f"Accessible profile connectivity: "
        f"{stats['connectivity_accessible_profile']['component_count']} components "
        f"(bridged {stats['connectivity_accessible_profile']['components_bridged_by_elevators']} "
        f"from {stats['connectivity_accessible_profile']['pathway_only_baseline']} baseline)"
    )
    logger.info("\nOutputs:")
    logger.info(f"  {graph_transitions_pkl}")
    logger.info(f"  {stats_json}")

    return 0


def contract_degree2_chains(
    graph: nx.MultiDiGraph,
    unit_centroids: list[tuple[float, float, str]],
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Contract degree-2 pathway chain segments into single edges.

    Implements DT-007: Contract Degree-2 Chains. The pinned fixture contracts
    44,952 directed arcs and 15,587 nodes to the measured baseline of 19,884
    arcs and 7,450 nodes. Protects junctions (≥3 pathway neighbors), transition
    endpoints, unit-proximity nodes, and transition-adjacent nodes.

    Args:
        graph: NetworkX MultiDiGraph from DT-006 with pathway + transition edges
        unit_centroids: List of (x, y, level_id) tuples for searchable units
            in EPSG:26910 coordinates

    Returns:
        (contracted_graph, stats) tuple where:
        - contracted_graph is NetworkX MultiDiGraph with contracted pathway edges
        - stats is dict with node/edge counts, contraction ratio, connectivity,
          shortest-path validation results

    Raises:
        RuntimeError: If cross-level chains detected or validation fails
    """
    logger.info("=== DT-007: Contract Degree-2 Chains ===")

    # Step 1: Identify protected nodes
    logger.info("Step 1/8: Identifying protected nodes...")
    protected_node_categories = _identify_protected_node_categories(
        graph, unit_centroids
    )
    protected_nodes = set().union(*protected_node_categories.values())
    contractible_nodes = {
        node
        for node in graph.nodes
        if _compute_physical_pathway_degree(graph, node) == 2
        and node not in protected_nodes
    }
    ambiguous_degree2_nodes = _identify_ambiguous_degree2_nodes(
        graph, contractible_nodes
    )
    contractible_nodes -= ambiguous_degree2_nodes
    boundary_nodes = set(graph.nodes) - contractible_nodes

    logger.info(f"  Protected nodes: {len(protected_nodes)} total")
    logger.info(
        f"  Ambiguous degree-2 nodes retained: {len(ambiguous_degree2_nodes)}"
    )
    for category, nodes in protected_node_categories.items():
        logger.info(f"    {category}: {len(nodes)}")

    # Step 2: Traverse chains and collect edges
    logger.info("Step 2/8: Traversing pathway chains from protected nodes...")
    chains = _traverse_chains(graph, boundary_nodes)

    logger.info(f"  Found {len(chains)} chains to contract")

    # Step 3: Build contracted graph
    logger.info("Step 3/8: Building contracted graph...")
    contracted_graph = nx.MultiDiGraph()
    contracted_graph.graph.update(graph.graph)

    # Add all chain boundaries with attributes. Degree-1 pathway endpoints are
    # boundaries even though they are not part of a protected category.
    for node in sorted(boundary_nodes):
        if node in graph.nodes:
            contracted_graph.add_node(node, **graph.nodes[node])

    # Step 4: Add contracted pathway edges
    logger.info("Step 4/8: Creating contracted pathway edges...")
    contracted_edges_added = 0

    for chain_data in chains:
        # Each chain produces a forward and reverse edge
        forward_key, reverse_key = _add_contracted_chain(
            contracted_graph, graph, chain_data
        )
        contracted_edges_added += 2

    logger.info(f"  Added {contracted_edges_added} contracted pathway arcs")

    # Step 5: Copy all transition edges unchanged
    logger.info("Step 5/8: Copying transition edges (stairs, elevator) unchanged...")
    transition_edges_added = 0

    for u, v, key, data in graph.edges(keys=True, data=True):
        if data.get("mode") in ("stairs", "elevator"):
            # Add nodes if not already present (transition-only nodes)
            if u not in contracted_graph.nodes:
                contracted_graph.add_node(u, **graph.nodes[u])
            if v not in contracted_graph.nodes:
                contracted_graph.add_node(v, **graph.nodes[v])

            # Copy edge with all attributes
            contracted_graph.add_edge(u, v, key=key, **data)
            transition_edges_added += 1

    logger.info(f"  Copied {transition_edges_added} transition arcs unchanged")

    # Step 6: Validate level consistency
    logger.info("Step 6/8: Validating level consistency...")
    _validate_level_consistency(contracted_graph, graph)

    # Step 7: Compute connectivity and basic stats
    logger.info("Step 7/8: Computing connectivity statistics...")
    stats = _compute_contraction_stats(
        graph,
        contracted_graph,
        protected_node_categories,
        len(chains),
        len(ambiguous_degree2_nodes),
    )

    # Step 8: Shortest-path validation
    logger.info("Step 8/8: Validating shortest-path preservation (20 pairs)...")
    shortest_path_stats = _validate_shortest_paths(
        graph, contracted_graph, protected_nodes
    )
    stats["shortest_path_validation"] = shortest_path_stats

    logger.info(
        f"  Shortest-path validation: {shortest_path_stats['pairs_tested']} pairs, "
        f"max delta: {shortest_path_stats['max_delta_m']:.4f}m"
    )

    logger.info("\n=== Contraction Complete ===")
    logger.info(f"Nodes: {stats['node_count']:,} (pre: {stats['pre_contraction_node_count']:,})")
    logger.info(
        f"Edges: {stats['edge_count']:,} (pre: {stats['pre_contraction_edge_count']:,})"
    )
    logger.info(
        f"Pathway arcs: {stats['pathway_arcs']:,} "
        f"(pre: {stats['pre_contraction_pathway_arcs']:,}, "
        f"reduction: {stats['pathway_contraction_ratio']:.1%})"
    )
    logger.info(
        f"Mean pathway length: {stats['mean_pathway_length_m']:.2f}m "
        f"(pre: {stats['pre_contraction_mean_pathway_length_m']:.2f}m)"
    )
    logger.info(
        f"Transition arcs preserved: {stats['transition_arcs']} "
        f"({stats['stairs_arcs']} stairs + {stats['elevator_arcs']} elevator)"
    )
    logger.info(
        f"Default profile: {stats['connectivity_default']['component_count']} components"
    )
    logger.info(
        f"Accessible profile: {stats['connectivity_accessible']['component_count']} components"
    )

    return contracted_graph, stats


def _compute_physical_pathway_degree(graph: nx.MultiDiGraph, node: NodeID) -> int:
    """Compute physical pathway degree: count of distinct pathway neighbors.

    Uses undirected physical topology: collapse parallel edges, merge forward/reverse,
    count only mode='pathway' edges, ignore transition edges.

    Args:
        graph: NetworkX MultiDiGraph
        node: Node ID tuple (x, y, vertical_order)

    Returns:
        Count of distinct pathway-connected neighbors
    """
    pathway_neighbors = set()

    # Outgoing edges
    for _u, v, data in graph.edges(node, data=True):
        if data.get("mode") == "pathway":
            pathway_neighbors.add(v)

    # Incoming edges
    for u, _v, data in graph.in_edges(node, data=True):
        if data.get("mode") == "pathway":
            pathway_neighbors.add(u)

    return len(pathway_neighbors)


def _identify_ambiguous_degree2_nodes(
    graph: nx.MultiDiGraph,
    candidates: set[NodeID],
) -> set[NodeID]:
    """Find degree-2 nodes whose two neighbors have unequal feature multiplicity."""
    ambiguous = set()
    for node in candidates:
        features_by_neighbor: dict[NodeID, set[str]] = defaultdict(set)
        for _u, neighbor, data in graph.edges(node, data=True):
            if data.get("mode") == "pathway":
                features_by_neighbor[neighbor].add(str(data["feature_id"]))
        for neighbor, _v, data in graph.in_edges(node, data=True):
            if data.get("mode") == "pathway":
                features_by_neighbor[neighbor].add(str(data["feature_id"]))
        if len({len(features) for features in features_by_neighbor.values()}) > 1:
            ambiguous.add(node)
    return ambiguous


def _identify_protected_nodes(
    graph: nx.MultiDiGraph,
    unit_centroids: list[tuple[float, float, str]],
) -> set[NodeID]:
    """Identify all protected nodes (never contracted).

    Protected nodes:
    1. Junctions: ≥3 distinct pathway neighbors in physical undirected topology
    2. Transition endpoints: is_transition_endpoint=True
    3. Unit-proximity: within 0.5m of any unit centroid on same level
    4. Transition-adjacent: incident to any stairs/elevator edge

    Args:
        graph: NetworkX MultiDiGraph from DT-006
        unit_centroids: List of (x, y, level_id) unit centroid coordinates

    Returns:
        Set of protected node IDs
    """
    categories = _identify_protected_node_categories(graph, unit_centroids)
    return set().union(*categories.values())


def _identify_protected_node_categories(
    graph: nx.MultiDiGraph,
    unit_centroids: list[tuple[float, float, str]],
) -> dict[str, set[NodeID]]:
    """Identify protected nodes grouped by their protection reason."""
    junctions = set()
    transition_endpoints = set()
    unit_proximity = set()
    transition_adjacent = set()

    # 1. Junctions (physical pathway degree ≥3)
    for node in graph.nodes():
        if _compute_physical_pathway_degree(graph, node) >= 3:
            junctions.add(node)

    # 2. Transition endpoints
    for node, attrs in graph.nodes(data=True):
        if attrs.get("is_transition_endpoint", False):
            transition_endpoints.add(node)

    # 3. Unit-proximity (within 0.5m of centroids on same level)
    for node, attrs in graph.nodes(data=True):
        node_x, node_y = node[0], node[1]
        node_level_ids = attrs.get("level_ids", set())
        for centroid_x, centroid_y, centroid_level_id in unit_centroids:
            # Check level match first
            if centroid_level_id not in node_level_ids:
                continue
            # Then check XY distance
            distance = ((node_x - centroid_x) ** 2 + (node_y - centroid_y) ** 2) ** 0.5
            if distance <= 0.5:  # 0.5m threshold
                unit_proximity.add(node)
                break

    # 4. Transition-adjacent (incident to stairs/elevator)
    for u, v, data in graph.edges(data=True):
        if data.get("mode") in ("stairs", "elevator"):
            transition_adjacent.add(u)
            transition_adjacent.add(v)

    return {
        "junctions": junctions,
        "transition_endpoints": transition_endpoints,
        "unit_proximity": unit_proximity,
        "transition_adjacent": transition_adjacent,
    }


def _traverse_chains(
    graph: nx.MultiDiGraph,
    boundary_nodes: set[NodeID],
) -> list[dict[str, Any]]:
    """Traverse pathway chains from protected nodes.

    A chain is a sequence of contractible pathway-degree-2 nodes between two
    protected nodes. Discovers each physical chain once by traversing forward,
    then creates both forward and reverse contracted edges.

    Args:
        graph: NetworkX MultiDiGraph
        boundary_nodes: Nodes that cannot be contracted

    Returns:
        List of chain dicts with keys: start, end, nodes, edges
    """
    physical_edges: dict[str, tuple[NodeID, NodeID]] = {}
    adjacency: dict[NodeID, list[tuple[NodeID, str]]] = defaultdict(list)
    for u, v, _key, data in graph.edges(keys=True, data=True):
        if data.get("mode") != "pathway":
            continue
        feature_id = str(data["feature_id"])
        if feature_id in physical_edges:
            continue
        physical_edges[feature_id] = (u, v)
        adjacency[u].append((v, feature_id))
        adjacency[v].append((u, feature_id))

    for incident in adjacency.values():
        incident.sort(key=lambda item: (item[0], item[1]))

    pairings: dict[tuple[NodeID, str], str] = {}

    def feature_sort_key(feature_id: str) -> tuple[float, str]:
        endpoint_a, endpoint_b = physical_edges[feature_id]
        lengths = [
            float(data.get("length_3d", 0.0))
            for data in graph.get_edge_data(endpoint_a, endpoint_b, default={}).values()
            if data.get("mode") == "pathway"
            and str(data.get("feature_id")) == feature_id
        ]
        return (min(lengths), feature_id)

    for node in sorted(set(graph.nodes) - boundary_nodes):
        by_neighbor: dict[NodeID, list[str]] = defaultdict(list)
        for neighbor, feature_id in adjacency[node]:
            by_neighbor[neighbor].append(feature_id)
        neighbor_a, neighbor_b = sorted(by_neighbor)
        for feature_a, feature_b in zip(
            sorted(by_neighbor[neighbor_a], key=feature_sort_key),
            sorted(by_neighbor[neighbor_b], key=feature_sort_key),
            strict=False,
        ):
            pairings[(node, feature_a)] = feature_b
            pairings[(node, feature_b)] = feature_a

    visited: set[str] = set()
    chains: list[dict[str, Any]] = []

    def oriented_edge(u: NodeID, v: NodeID, feature_id: str) -> tuple[Any, ...]:
        candidates = [
            (key, data)
            for key, data in graph.get_edge_data(u, v, default={}).items()
            if data.get("mode") == "pathway"
            and str(data.get("feature_id")) == feature_id
        ]
        if not candidates:
            raise RuntimeError(
                f"Missing directed pathway arc for feature {feature_id}: {u} -> {v}"
            )
        key, data = sorted(candidates, key=lambda item: str(item[0]))[0]
        return (u, v, key, data)

    def other_endpoint(node: NodeID, feature_id: str) -> NodeID:
        endpoint_a, endpoint_b = physical_edges[feature_id]
        return endpoint_b if node == endpoint_a else endpoint_a

    def walk(start: NodeID, first_fid: str) -> dict[str, Any]:
        nodes = [start]
        edges = []
        current = start
        feature_id = first_fid

        while True:
            next_node = other_endpoint(current, feature_id)
            visited.add(feature_id)
            nodes.append(next_node)
            edges.append(oriented_edge(current, next_node, feature_id))
            paired_feature = pairings.get((next_node, feature_id))
            if paired_feature is None or paired_feature in visited:
                break
            current = next_node
            feature_id = paired_feature

        return {"start": nodes[0], "end": nodes[-1], "nodes": nodes, "edges": edges}

    terminal_half_edges = sorted(
        (node, feature_id)
        for node, incident in adjacency.items()
        for _neighbor, feature_id in incident
        if (node, feature_id) not in pairings
    )
    for start, feature_id in terminal_half_edges:
        if feature_id not in visited:
            chains.append(walk(start, feature_id))

    # Closed paired trails have no terminal half-edge. Anchor each at the
    # lowest endpoint of its lowest unvisited feature.
    while len(visited) < len(physical_edges):
        feature_id = min(set(physical_edges) - visited)
        start = min(physical_edges[feature_id])
        if feature_id not in visited:
            chains.append(walk(start, feature_id))

    return chains


def _add_contracted_chain(
    contracted_graph: nx.MultiDiGraph,
    source_graph: nx.MultiDiGraph,
    chain: dict[str, Any],
) -> tuple[str, str]:
    """Add a contracted chain as forward and reverse edges.

    Args:
        contracted_graph: Target graph to add edges to
        source_graph: Source graph with original edges
        chain: Chain dict with start, end, nodes, edges

    Returns:
        (forward_key, reverse_key) tuple
    """
    start = chain["start"]
    end = chain["end"]
    edges = chain["edges"]

    # Collect attributes from segments
    length_3d = sum(d.get("length_3d", 0.0) for u, v, k, d in edges)
    level_id = edges[0][3].get("level_id")  # All segments must share level_id
    physical_ids = sorted(str(d["feature_id"]) for u, v, k, d in edges)
    exact_mode = source_graph.graph.get("topology_mode") == EXACT_MODE
    original_fids = (
        sorted({str(d.get("source_feature_id", d["feature_id"])) for u, v, k, d in edges})
        if exact_mode else physical_ids
    )
    source_spans = [span for _u, _v, _k, data in edges for span in data.get("source_spans", [])]
    extra = ({"source_spans": source_spans, "original_segment_ids": physical_ids,
              "source_spans_complete": all(data.get("source_spans_complete", False)
                                           for _u, _v, _k, data in edges)} if exact_mode else {})
    contracted_segment_count = len(edges)

    # Merge geometries: concatenate coordinates, drop intermediate duplicates
    all_coords = []
    for i, (_u, _v, _k, d) in enumerate(edges):
        geom = d.get("geometry")
        if geom is None:
            continue
        coords = list(geom.coords)
        if i == 0:
            # First segment: include all coords
            all_coords.extend(coords)
        else:
            # Subsequent segments: skip first coord (duplicate of previous end)
            all_coords.extend(coords[1:])

    merged_geom = LineString(all_coords)

    # Generate deterministic chain ID
    # Use sorted endpoint nodes + sorted original FIDs
    endpoints_str = f"{sorted([start, end])}"
    fids_str = f"{physical_ids}"
    chain_str = f"{endpoints_str}_{fids_str}"
    chain_hash = hashlib.sha256(chain_str.encode()).hexdigest()[:16]
    chain_id = f"CONTRACTED_{chain_hash}"

    # Add forward edge
    forward_key = f"PW_{chain_id}"
    contracted_graph.add_edge(
        start,
        end,
        key=forward_key,
        length_3d=length_3d,
        mode="pathway",
        level_id=level_id,
        geometry=merged_geom,
        original_feature_ids=original_fids,
        contracted_segment_count=contracted_segment_count,
        **extra,
    )

    # Add reverse edge with reversed geometry
    reverse_key = f"PW_{chain_id}_R"
    reverse_geom = LineString(list(reversed(merged_geom.coords)))
    reverse_extra = {**extra, "source_spans": reverse_spans(source_spans)} if exact_mode else {}
    contracted_graph.add_edge(
        end,
        start,
        key=reverse_key,
        length_3d=length_3d,
        mode="pathway",
        level_id=level_id,
        geometry=reverse_geom,
        original_feature_ids=original_fids,
        contracted_segment_count=contracted_segment_count,
        **reverse_extra,
    )

    return forward_key, reverse_key


def _validate_level_consistency(
    contracted_graph: nx.MultiDiGraph,
    source_graph: nx.MultiDiGraph,
) -> None:
    """Validate that all segments in contracted chains share the same level_id.

    Args:
        contracted_graph: Contracted graph
        source_graph: Pre-contraction graph

    Raises:
        RuntimeError: If any cross-level chains detected
    """
    # Build feature_id to level_id index for fast lookup
    fid_to_level = {}
    for _u, _v, _k, d in source_graph.edges(keys=True, data=True):
        if d.get("mode") == "pathway":
            fid = d.get("source_feature_id", d.get("feature_id"))
            level_id = d.get("level_id")
            if fid and level_id:
                fid_to_level[fid] = level_id

    cross_level_chains = []

    for u, v, k, data in contracted_graph.edges(keys=True, data=True):
        if data.get("mode") != "pathway":
            continue
        if data.get("contracted_segment_count", 1) <= 1:
            continue

        original_fids = data.get("original_feature_ids", [])

        # Collect levels from original segments using index
        levels: set[str] = {
            fid_to_level[fid] for fid in original_fids if fid in fid_to_level
        }

        if len(levels) > 1:
            cross_level_chains.append({
                "edge": (u, v, k),
                "levels": sorted(levels),
                "fids": original_fids,
            })

    if cross_level_chains:
        raise RuntimeError(
            f"Found {len(cross_level_chains)} cross-level pathway chains. "
            f"This is a data error: pathways should not cross levels without a transition. "
            f"Sample: {cross_level_chains[:3]}"
        )


def _compute_contraction_stats(
    graph_pre: nx.MultiDiGraph,
    graph_post: nx.MultiDiGraph,
    protected_node_categories: dict[str, set[NodeID]],
    chain_count: int,
    ambiguous_degree2_nodes_retained: int = 0,
) -> dict[str, Any]:
    """Compute contraction statistics.

    Args:
        graph_pre: Pre-contraction graph
        graph_post: Contracted graph
        protected_node_categories: Protected nodes grouped by protection reason
        chain_count: Number of chains contracted

    Returns:
        Statistics dict
    """
    # Pre-contraction counts
    pre_node_count = graph_pre.number_of_nodes()
    pre_edge_count = graph_pre.number_of_edges()
    pre_pathway_arcs = sum(
        1 for u, v, k, d in graph_pre.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    )
    pre_pathway_lengths = [
        d.get("length_3d", 0.0)
        for u, v, k, d in graph_pre.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    ]
    pre_mean_pathway_length = (
        sum(pre_pathway_lengths) / len(pre_pathway_lengths) if pre_pathway_lengths else 0.0
    )

    # Post-contraction counts
    node_count = graph_post.number_of_nodes()
    edge_count = graph_post.number_of_edges()

    pathway_arcs = sum(
        1 for u, v, k, d in graph_post.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    )
    stairs_arcs = sum(
        1 for u, v, k, d in graph_post.edges(keys=True, data=True)
        if d.get("mode") == "stairs"
    )
    elevator_arcs = sum(
        1 for u, v, k, d in graph_post.edges(keys=True, data=True)
        if d.get("mode") == "elevator"
    )
    transition_arcs = stairs_arcs + elevator_arcs

    pathway_lengths = [
        d.get("length_3d", 0.0)
        for u, v, k, d in graph_post.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    ]
    mean_pathway_length = (
        sum(pathway_lengths) / len(pathway_lengths) if pathway_lengths else 0.0
    )

    # Contraction ratio
    pathway_contraction_ratio = (
        (pre_pathway_arcs - pathway_arcs) / pre_pathway_arcs if pre_pathway_arcs > 0 else 0.0
    )

    # Mean degree
    degrees = dict(graph_post.degree())
    mean_degree = sum(degrees.values()) / node_count if node_count > 0 else 0.0

    # Connectivity statistics
    # Default profile: pathway + stairs + elevator
    default_graph = nx.Graph()
    for u, v, data in graph_post.edges(data=True):
        if data.get("mode") in ("pathway", "stairs", "elevator"):
            default_graph.add_edge(u, v)

    default_component_count = nx.number_connected_components(default_graph)
    default_components = list(nx.connected_components(default_graph))
    default_largest = max((len(c) for c in default_components), default=0)

    # Accessible profile: pathway + elevator only
    accessible_graph = nx.Graph()
    for u, v, data in graph_post.edges(data=True):
        if data.get("mode") in ("pathway", "elevator"):
            accessible_graph.add_edge(u, v)

    accessible_component_count = nx.number_connected_components(accessible_graph)
    accessible_components = list(nx.connected_components(accessible_graph))
    accessible_largest = max((len(c) for c in accessible_components), default=0)

    protected_nodes = set().union(*protected_node_categories.values())
    protected_node_counts = {
        category: len(nodes)
        for category, nodes in protected_node_categories.items()
    }
    protected_node_counts["total"] = len(protected_nodes)

    stats = {
        "etl_version": "0.1.0",
        "timestamp": datetime.now().astimezone().isoformat(),
        "pre_contraction_node_count": pre_node_count,
        "pre_contraction_edge_count": pre_edge_count,
        "pre_contraction_pathway_arcs": pre_pathway_arcs,
        "pre_contraction_mean_pathway_length_m": round(pre_mean_pathway_length, 2),
        "node_count": node_count,
        "edge_count": edge_count,
        "pathway_arcs": pathway_arcs,
        "stairs_arcs": stairs_arcs,
        "elevator_arcs": elevator_arcs,
        "transition_arcs": transition_arcs,
        "mean_pathway_length_m": round(mean_pathway_length, 2),
        "mean_degree": round(mean_degree, 2),
        "chains_contracted": chain_count,
        "ambiguous_degree2_nodes_retained": ambiguous_degree2_nodes_retained,
        "pathway_contraction_ratio": round(pathway_contraction_ratio, 4),
        "protected_node_count": len(protected_nodes),
        "connectivity_default": {
            "component_count": default_component_count,
            "largest_component_size": default_largest,
        },
        "connectivity_accessible": {
            "component_count": accessible_component_count,
            "largest_component_size": accessible_largest,
        },
        "pathway_arc_count": pathway_arcs,
        "transition_arc_count": transition_arcs,
        "contraction_ratio": round(pathway_contraction_ratio, 4),
        "mean_pathway_length": round(mean_pathway_length, 2),
        "protected_node_counts": protected_node_counts,
        "component_counts": {
            "default": default_component_count,
            "elevator_only": accessible_component_count,
        },
    }

    return stats


def _validate_shortest_paths(
    graph_pre: nx.MultiDiGraph,
    graph_post: nx.MultiDiGraph,
    protected_nodes: set[NodeID],
) -> dict[str, Any]:
    """Validate shortest-path preservation across 20 connected protected-node pairs.

    Args:
        graph_pre: Pre-contraction graph
        graph_post: Contracted graph
        protected_nodes: Set of protected nodes

    Returns:
        Stats dict with pairs_tested, pairs_matched, max_delta_m
    """
    # Build default profile graphs (pathway + stairs + elevator)
    def build_profile_graph(graph):
        profile = nx.Graph()
        for u, v, data in graph.edges(data=True):
            if data.get("mode") in ("pathway", "stairs", "elevator"):
                weight = data.get("length_3d", 1.0)
                # Accumulate min weight for parallel edges
                if profile.has_edge(u, v):
                    profile[u][v]["weight"] = min(profile[u][v]["weight"], weight)
                else:
                    profile.add_edge(u, v, weight=weight)
        return profile

    profile_pre = build_profile_graph(graph_pre)
    profile_post = build_profile_graph(graph_post)

    # Get components with ≥2 protected nodes
    rng = random.Random(42)
    component_pairs = []
    components_pre = sorted(
        (
            sorted(component & protected_nodes)
            for component in nx.connected_components(profile_pre)
            if len(component & protected_nodes) >= 2
        ),
        key=lambda nodes: nodes[0],
    )
    for nodes in components_pre:
        eligible_pairs = list(combinations(nodes, 2))
        rng.shuffle(eligible_pairs)
        component_pairs.append(eligible_pairs)

    pairs = []
    while len(pairs) < 20 and any(component_pairs):
        for eligible_pairs in component_pairs:
            if eligible_pairs and len(pairs) < 20:
                pairs.append(eligible_pairs.pop())

    if len(pairs) < 20:
        raise RuntimeError(
            f"Could not select 20 connected protected-node pairs. "
            f"Found only {len(pairs)} pairs."
        )

    # Compare shortest paths
    max_delta = 0.0
    mismatches = []

    for src, tgt in pairs:
        try:
            dist_pre = nx.shortest_path_length(profile_pre, src, tgt, weight="weight")
        except nx.NetworkXNoPath as error:
            raise RuntimeError(
                f"Pair ({src}, {tgt}) disconnected in pre-contraction graph"
            ) from error

        try:
            dist_post = nx.shortest_path_length(profile_post, src, tgt, weight="weight")
        except nx.NetworkXNoPath as error:
            raise RuntimeError(
                f"Pair ({src}, {tgt}) connected pre-contraction but disconnected post-contraction"
            ) from error

        delta = abs(dist_pre - dist_post)
        max_delta = max(max_delta, delta)

        if delta > 0.01:  # 1 cm tolerance
            mismatches.append((src, tgt, dist_pre, dist_post, delta))

    if mismatches:
        raise RuntimeError(
            f"Found {len(mismatches)} pairs with distance mismatch >0.01m. "
            f"Sample: {mismatches[:3]}"
        )

    return {
        "pairs_tested": len(pairs),
        "pairs_matched": len(pairs),
        "max_delta_m": round(max_delta, 4),
    }


def run_graph_contract(output_dir: Path) -> int:
    """Run graph-contract ETL step: contract degree-2 pathway chains.

    Loads graph_with_transitions.pkl from DT-006 and wayfinding.gpkg unit_26910
    layer, contracts pathway chains, and outputs graph_contracted.pkl and
    graph_contracted_stats.json.

    Args:
        output_dir: Directory for output artifacts (typically /workspace/build)

    Returns:
        Exit code (0 = success)
    """
    import pickle

    def artifact_entry(path: Path) -> dict[str, str]:
        relative_path = path.relative_to(output_dir.parent).as_posix()
        return {
            "path": relative_path,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    graph_transitions_pkl = output_dir / "graph_with_transitions.pkl"
    gpkg_path = output_dir / "wayfinding.gpkg"

    # Validate inputs exist
    if not graph_transitions_pkl.exists():
        logger.error(f"graph_with_transitions.pkl not found: {graph_transitions_pkl}")
        logger.error("Run 'make etl-graph-transitions' first.")
        return 1

    if not gpkg_path.exists():
        logger.error(f"GeoPackage not found: {gpkg_path}")
        logger.error("Run 'make etl-extract' and 'make etl-normalise' first.")
        return 1

    logger.info("=== DT-007: Contract Degree-2 Chains ===")
    logger.info(f"Inputs: {graph_transitions_pkl}, {gpkg_path}")

    # Load graph
    logger.info("Loading graph_with_transitions.pkl...")
    with open(graph_transitions_pkl, "rb") as f:
        graph = pickle.load(f)

    # Load unit centroids from GeoPackage
    logger.info("Loading unit centroids from unit_26910 layer...")
    ds = ogr.Open(str(gpkg_path), 0)  # Read-only
    if ds is None:
        logger.error(f"Cannot open GeoPackage: {gpkg_path}")
        return 1

    layer = ds.GetLayerByName("unit_26910")
    if layer is None:
        logger.error("unit_26910 layer not found in GeoPackage")
        return 1

    unit_centroids = []
    for feature in layer:
        centroid_wkt = feature.GetField("centroid_26910")
        level_id = feature.GetField("level_id")
        if centroid_wkt and level_id:
            point = cast(Point, wkt.loads(centroid_wkt))
            unit_centroids.append((point.x, point.y, level_id))

    ds = None  # Close dataset

    logger.info(f"Loaded {len(unit_centroids)} unit centroids")

    # Contract chains
    logger.info("Contracting degree-2 pathway chains...")
    contracted_graph, stats = contract_degree2_chains(graph, unit_centroids)

    # Serialize outputs
    graph_contracted_pkl = output_dir / "graph_contracted.pkl"
    stats_json = output_dir / "graph_contracted_stats.json"

    logger.info(f"Writing graph to {graph_contracted_pkl}...")
    with open(graph_contracted_pkl, "wb") as f:
        pickle.dump(contracted_graph, f, protocol=5)

    stats["lineage"] = {
        "inputs": sorted(
            [artifact_entry(graph_transitions_pkl), artifact_entry(gpkg_path)],
            key=lambda entry: entry["path"],
        ),
        "outputs": [artifact_entry(graph_contracted_pkl)],
    }

    logger.info(f"Writing stats to {stats_json}...")
    with open(stats_json, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("\n=== Contraction Complete ===")
    logger.info(f"Nodes: {stats['node_count']:,} (pre: {stats['pre_contraction_node_count']:,})")
    logger.info(f"Edges: {stats['edge_count']:,} (pre: {stats['pre_contraction_edge_count']:,})")
    logger.info(
        f"Pathway arcs: {stats['pathway_arcs']:,} "
        f"(pre: {stats['pre_contraction_pathway_arcs']:,}, "
        f"reduction: {stats['pathway_contraction_ratio']:.1%})"
    )
    logger.info(f"Mean pathway length: {stats['mean_pathway_length_m']:.2f}m")
    logger.info(
        f"Transition arcs preserved: {stats['transition_arcs']} "
        f"({stats['stairs_arcs']} stairs + {stats['elevator_arcs']} elevator)"
    )
    logger.info(
        f"Default profile: {stats['connectivity_default']['component_count']} components"
    )
    logger.info(
        f"Accessible profile: {stats['connectivity_accessible']['component_count']} components"
    )
    logger.info("\nOutputs:")
    logger.info(f"  {graph_contracted_pkl}")
    logger.info(f"  {stats_json}")

    return 0
