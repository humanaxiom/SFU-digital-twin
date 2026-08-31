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

import json
import logging
from collections import defaultdict
from datetime import datetime
from math import floor
from pathlib import Path
from typing import Any, cast

import networkx as nx
from osgeo import ogr  # pyright: ignore[reportMissingImports]
from shapely import wkt
from shapely.geometry import LineString, MultiLineString

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


def run_graph_raw(output_dir: Path) -> int:
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
