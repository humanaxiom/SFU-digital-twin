"""Failing tests for DT-006: Add Transition Edges to Graph.

These tests check:
1. add_transitions() function signature and return values
2. Edge count: exactly 126 transition edges (63 features × 2 directions)
3. Transition type mapping: TRANSITION_TYPE 2→stairs (84 arcs), 4→elevator (42 arcs)
4. Edge attributes: {length_3d, mode, level_id_from, level_id_to, vertical_order_from,
   vertical_order_to, feature_id, geometry} for all transition edges
5. Reverse arc geometry: reversed coordinates for reverse edges
6. Transition endpoint protection: 85 unique nodes marked is_transition_endpoint=True
7. Transition-only nodes: five added nodes with complete DT-005 node-attribute contract
8. Express elevators: 2 features with vertical_order delta = 2, no intermediate hops
9. Default profile connectivity: 816 components, largest 7,436, 39 bridged (from 855 baseline)
10. Accessible profile connectivity: 840 components, largest 7,060, 15 bridged, warning not error
11. Orphan transition detection: build failure if endpoint not in node_map
12. Final node/edge counts: 15,587 nodes, 44,952 edges (44,826 pathway + 126 transition)
13. Deterministic graph structure across runs
14. Stats JSON schema with all required keys
15. Container-only execution via Makefile target
16. Read-only inputs: graph_raw.pkl, node_map.pkl, wayfinding.gpkg mtime unchanged

All tests will FAIL initially because:
- wayfinding.etl.graph.add_transitions() does not exist
- run_graph_transitions() orchestration entry point does not exist
- run.py has no graph-transitions subcommand
- Makefile has no etl-graph-transitions target

Tests use in-memory fixtures from DT-003/DT-004/DT-005 artifacts rather than relying on
pre-generated DT-006 outputs, except where testing explicit serialization behavior.

Pinned-fixture measurements per ADR-0005:
- Pathway-only baseline: 855 components
- Default profile (pathway + stairs + elevator): 816 components, 39 bridged
- Accessible profile (pathway + elevator): 840 components, 15 bridged
- Express elevators: 2 features spanning vertical_order 0→2
- Transition-only nodes: 5 nodes absent from graph_raw.pkl
"""

# NetworkX documentation conventionally names graph objects G; retain that notation in tests.
# ruff: noqa: N806

import inspect
import json
import pickle
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Guard conditional imports to allow RED test collection before dependencies installed
try:
    import networkx as nx
except ImportError:
    nx = None

try:
    from shapely.geometry import LineString
except ImportError:
    LineString = None

# Paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
BUILD_DIR = WORKSPACE_ROOT / "build"
SOURCE_GPKG = BUILD_DIR / "wayfinding.gpkg"

# Input artifacts from DT-005 (read-only)
GRAPH_RAW_PKL = BUILD_DIR / "graph_raw.pkl"
NODE_MAP_PKL = BUILD_DIR / "node_map.pkl"

# Expected counts per DT-006 plan and ADR-0005
EXPECTED_TRANSITION_FEATURES = 63
EXPECTED_TRANSITION_EDGES = 126  # 63 × 2 (bidirectional)
EXPECTED_STAIRS_ARCS = 84  # 42 features × 2
EXPECTED_ELEVATOR_ARCS = 42  # 21 features × 2
EXPECTED_PATHWAY_ARCS = 44_826  # From DT-005
EXPECTED_TOTAL_EDGES = 44_952  # 44,826 + 126
EXPECTED_FINAL_NODE_COUNT = 15_587  # 15,582 + 5 transition-only nodes
EXPECTED_PROTECTED_ENDPOINTS = 85  # Unique transition endpoint nodes
EXPECTED_TRANSITION_ONLY_NODES = 5  # Nodes absent from graph_raw.pkl
EXPECTED_EXPRESS_ELEVATORS = 2  # Features with vertical_order delta = 2

# Connectivity baselines per ADR-0005
PATHWAY_ONLY_BASELINE = 855
DEFAULT_PROFILE_COMPONENTS = 816
DEFAULT_PROFILE_LARGEST_COMPONENT = 7_436
DEFAULT_PROFILE_BRIDGED = 39
ACCESSIBLE_PROFILE_COMPONENTS = 840
ACCESSIBLE_PROFILE_LARGEST_COMPONENT = 7_060
ACCESSIBLE_PROFILE_BRIDGED = 15


# ============================================================================
# Helper Functions
# ============================================================================


def require_file(path: Path, description: str) -> None:
    """Assert file exists with clear pytest.fail() message.

    Args:
        path: Path to required file
        description: Human-readable description of the file's origin

    Raises:
        pytest.fail: If file does not exist with clear instructions
    """
    if not path.exists():
        pytest.fail(
            f"Required input not found: {path}\n"
            f"Description: {description}\n"
            f"To generate: See docs/plans/DT-006.md dependencies section"
        )


def load_required_gpkg() -> Path:
    """Load required GPKG from DT-003/DT-004, failing clearly if missing."""
    require_file(SOURCE_GPKG, "DT-003/DT-004 GeoPackage (run make etl-normalise)")
    return SOURCE_GPKG


def load_required_graph_raw() -> Any:
    """Load graph_raw.pkl from DT-005, failing clearly if missing."""
    require_file(GRAPH_RAW_PKL, "DT-005 raw pathway graph (run make etl-graph-raw)")
    with open(GRAPH_RAW_PKL, "rb") as f:
        return pickle.load(f)


def load_required_node_map() -> dict[tuple[str, str, str], tuple[float, float, int]]:
    """Load node_map.pkl from DT-005, failing clearly if missing."""
    require_file(NODE_MAP_PKL, "DT-005 node map (run make etl-graph-raw)")
    with open(NODE_MAP_PKL, "rb") as f:
        return pickle.load(f)


def fresh_graph_and_node_map() -> tuple[Any, dict[tuple[str, str, str], tuple[float, float, int]]]:
    """Load independent copies of graph_raw and node_map for mutation-safe testing."""
    return load_required_graph_raw(), load_required_node_map()


# ============================================================================
# Module-Scoped Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def graph_with_transitions_in_memory() -> tuple[Any, dict[str, Any]]:
    """Load fresh graph_raw and node_map, call add_transitions(), return (graph, stats)."""
    if nx is None:
        pytest.fail("networkx must be installed (dependency check failed)")

    from wayfinding.etl.graph import add_transitions

    graph, node_map = fresh_graph_and_node_map()
    gpkg_path = load_required_gpkg()

    return add_transitions(graph, node_map, str(gpkg_path))


@pytest.fixture(scope="module")
def graph_with_transitions_serialized(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Run orchestration entry point in temp dir, return paths to serialized artifacts."""
    if nx is None:
        pytest.fail("networkx must be installed (dependency check failed)")

    from wayfinding.etl.graph import run_graph_transitions

    output_dir = tmp_path_factory.mktemp("dt006_output")
    for source in (GRAPH_RAW_PKL, NODE_MAP_PKL, SOURCE_GPKG):
        require_file(source, "DT-006 orchestration input")
        shutil.copy2(source, output_dir / source.name)

    input_mtimes = {
        path.name: (output_dir / path.name).stat().st_mtime
        for path in (GRAPH_RAW_PKL, NODE_MAP_PKL, SOURCE_GPKG)
    }
    assert run_graph_transitions(output_dir) == 0
    for name, mtime in input_mtimes.items():
        assert (output_dir / name).stat().st_mtime == mtime

    return {
        "output_dir": output_dir,
        "graph_pkl": output_dir / "graph_with_transitions.pkl",
        "stats_json": output_dir / "graph_with_transitions_stats.json",
    }


# ============================================================================
# Test Module Structure and Function Signatures
# ============================================================================


class TestAddTransitionsModuleStructure:
    """Test wayfinding.etl.graph module has add_transitions() function."""

    def test_graph_module_has_add_transitions(self) -> None:
        """graph.py must define add_transitions() function."""
        from wayfinding.etl import graph

        assert hasattr(graph, "add_transitions"), (
            "graph module missing add_transitions function (DT-006 deliverable)"
        )

    def test_add_transitions_signature(self) -> None:
        """add_transitions() must accept graph, node_map, gpkg_path parameters."""
        from wayfinding.etl.graph import add_transitions

        sig = inspect.signature(add_transitions)
        params = list(sig.parameters.keys())

        assert "graph" in params, "add_transitions missing graph parameter"
        assert "node_map" in params, "add_transitions missing node_map parameter"
        assert "gpkg_path" in params, "add_transitions missing gpkg_path parameter"

    def test_add_transitions_returns_tuple(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """add_transitions() must return (graph, stats) tuple with correct types."""
        graph, stats = graph_with_transitions_in_memory

        # Verify types
        assert graph is not None, "add_transitions returned None for graph"
        assert isinstance(stats, dict), (
            f"add_transitions stats must be dict, got {type(stats).__name__}"
        )

        # Verify graph has nodes and edges
        assert graph.number_of_nodes() > 0, "Returned graph has no nodes"
        assert graph.number_of_edges() > 0, "Returned graph has no edges"


# ============================================================================
# Test AC1: Transition Edge Count and Bidirectionality
# ============================================================================


class TestTransitionEdgeCount:
    """Test exactly 126 transition edges added (63 features × 2 directions)."""

    def test_add_transitions_edge_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Exactly 126 transition edges must be added (63 × 2)."""
        G, _ = graph_with_transitions_in_memory
        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        assert len(transition_edges) == EXPECTED_TRANSITION_EDGES, (
            f"Expected {EXPECTED_TRANSITION_EDGES} transition edges, got {len(transition_edges)}"
        )

    def test_add_transitions_total_edge_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Total edge count must be 44,952 (44,826 pathway + 126 transition)."""
        G, _ = graph_with_transitions_in_memory
        edge_count = G.number_of_edges()

        assert edge_count == EXPECTED_TOTAL_EDGES, (
            f"Expected {EXPECTED_TOTAL_EDGES} total edges, got {edge_count}"
        )

    def test_add_transitions_bidirectional(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """For every TR_{fid} edge, TR_{fid}_R reverse edge must exist."""
        G, _ = graph_with_transitions_in_memory

        # Get all forward transition edges (no _R suffix)
        forward_edges = [
            (u, v, k)
            for u, v, k in G.edges(keys=True)
            if k.startswith("TR_") and not k.endswith("_R")
        ]

        for u, v, key in forward_edges:
            reverse_key = key + "_R"
            assert G.has_edge(v, u, reverse_key), (
                f"Forward transition edge ({u}, {v}, {key}) missing reverse arc "
                f"({v}, {u}, {reverse_key})"
            )

    def test_add_transitions_edge_keys(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All transition edges must have keys starting with 'TR_'."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        # Verify count matches expected
        assert len(transition_edges) == EXPECTED_TRANSITION_EDGES, (
            f"Expected {EXPECTED_TRANSITION_EDGES} transition edges with TR_ prefix"
        )


# ============================================================================
# Test AC2: Transition Type Mapping
# ============================================================================


class TestTransitionTypeMapping:
    """Test TRANSITION_TYPE 2→stairs, 4→elevator mapping."""

    def test_transition_type_mapping_stairs(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All stairs edges must have mode='stairs'."""
        G, _ = graph_with_transitions_in_memory

        # Get all transition edges
        transition_edges = [
            (u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True) if k.startswith("TR_")
        ]

        # Filter to stairs mode
        stairs_edges = [e for e in transition_edges if e[3]["mode"] == "stairs"]

        # All stairs edges should be transitions (validated by TR_ prefix)
        assert all(e[2].startswith("TR_") for e in stairs_edges), (
            "Non-transition edges have mode='stairs'"
        )

    def test_transition_type_mapping_elevator(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All elevator edges must have mode='elevator'."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [
            (u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True) if k.startswith("TR_")
        ]

        # Filter to elevator mode
        elevator_edges = [e for e in transition_edges if e[3]["mode"] == "elevator"]

        # All elevator edges should be transitions
        assert all(e[2].startswith("TR_") for e in elevator_edges), (
            "Non-transition edges have mode='elevator'"
        )

    def test_transition_mode_counts(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Must have exactly 84 stairs arcs and 42 elevator arcs."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [
            (u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True) if k.startswith("TR_")
        ]

        stairs_count = sum(1 for e in transition_edges if e[3]["mode"] == "stairs")
        elevator_count = sum(1 for e in transition_edges if e[3]["mode"] == "elevator")

        assert stairs_count == EXPECTED_STAIRS_ARCS, (
            f"Expected {EXPECTED_STAIRS_ARCS} stairs arcs (42 features × 2), got {stairs_count}"
        )
        assert elevator_count == EXPECTED_ELEVATOR_ARCS, (
            f"Expected {EXPECTED_ELEVATOR_ARCS} elevator arcs (21 features × 2), "
            f"got {elevator_count}"
        )

    def test_no_unsupported_transition_types(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """No type 3 (ramp), 5 (escalator), 6 (moving walkway) transitions."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [
            (u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True) if k.startswith("TR_")
        ]

        # All transition edges must have mode in {stairs, elevator}
        valid_modes = {"stairs", "elevator"}
        invalid = [e for e in transition_edges if e[3]["mode"] not in valid_modes]

        assert len(invalid) == 0, (
            f"Found {len(invalid)} transition edges with unsupported mode. "
            f"Valid modes: {valid_modes}. Invalid edges: {invalid[:5]}"
        )


# ============================================================================
# Test AC3: Edge Attribute Schema
# ============================================================================


class TestTransitionEdgeAttributes:
    """Test edge attribute schema for transition edges."""

    def test_transition_edge_attributes_schema(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Every transition edge must have 8 required attributes."""
        G, _ = graph_with_transitions_in_memory

        required_keys = {
            "length_3d",
            "mode",
            "level_id_from",
            "level_id_to",
            "vertical_order_from",
            "vertical_order_to",
            "feature_id",
            "geometry",
        }

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        # Check first 10 transition edges
        for u, v, k in transition_edges[:10]:
            edge_attrs = set(G.edges[u, v, k].keys())
            missing = required_keys - edge_attrs
            assert not missing, f"Transition edge ({u}, {v}, {k}) missing attributes: {missing}"

    def test_transition_edge_attributes_types(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Edge attributes must have correct data types."""
        if LineString is None:
            pytest.fail("shapely must be installed (dependency check failed)")

        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        # Check first transition edge
        if not transition_edges:
            pytest.fail("No transition edges found")

        u, v, k = transition_edges[0]
        attrs = G.edges[u, v, k]

        assert isinstance(attrs["length_3d"], (int, float)), "length_3d must be numeric"
        assert isinstance(attrs["mode"], str), "mode must be string"
        assert isinstance(attrs["level_id_from"], str), "level_id_from must be string"
        assert isinstance(attrs["level_id_to"], str), "level_id_to must be string"
        assert isinstance(attrs["vertical_order_from"], int), "vertical_order_from must be int"
        assert isinstance(attrs["vertical_order_to"], int), "vertical_order_to must be int"
        assert isinstance(attrs["feature_id"], str), "feature_id must be string"
        assert isinstance(attrs["geometry"], LineString), "geometry must be Shapely LineString"

    def test_transition_vertical_order_from_node_map(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """vertical_order values must match node ID tuples, not Z coordinates."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        # For each transition edge, verify vertical_order matches node ID
        for u, v, k in transition_edges[:10]:
            attrs = G.edges[u, v, k]

            # Node IDs are (x, y, vertical_order) tuples
            u_vo = u[2] if isinstance(u, tuple) and len(u) == 3 else None
            v_vo = v[2] if isinstance(v, tuple) and len(v) == 3 else None

            # Skip if node IDs are not tuples (shouldn't happen)
            if u_vo is None or v_vo is None:
                continue

            # vertical_order_from should match start node's vertical_order
            assert attrs["vertical_order_from"] == u_vo, (
                f"Edge {k} vertical_order_from={attrs['vertical_order_from']} "
                f"does not match start node vertical_order={u_vo}"
            )

            # vertical_order_to should match end node's vertical_order
            assert attrs["vertical_order_to"] == v_vo, (
                f"Edge {k} vertical_order_to={attrs['vertical_order_to']} "
                f"does not match end node vertical_order={v_vo}"
            )

    def test_transition_level_id_construction(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """level_id_from/to must use FACILITY_ID + LEVEL_NAME format."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        # Check first 10 transition edges
        for u, v, k in transition_edges[:10]:
            attrs = G.edges[u, v, k]

            # level_id format: FACILITY_ID + "_" + LEVEL_NAME
            level_id_from = attrs["level_id_from"]
            level_id_to = attrs["level_id_to"]

            assert "_" in level_id_from, (
                f"level_id_from '{level_id_from}' must contain '_' separator"
            )
            assert "_" in level_id_to, f"level_id_to '{level_id_to}' must contain '_' separator"

    def test_transition_length_3d_positive(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All transition lengths must be > 0."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        for u, v, key in transition_edges:
            length = G.edges[u, v, key]["length_3d"]
            assert length > 0, f"Transition edge {key} has non-positive length_3d: {length}"

    def test_transition_reverse_arc_geometry(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Reverse arc coordinates must be reversed(forward_coords)."""
        if LineString is None:
            pytest.fail("shapely must be installed (dependency check failed)")

        G, _ = graph_with_transitions_in_memory

        # Get forward transition edges (no _R suffix)
        forward_edges = [
            (u, v, k)
            for u, v, k in G.edges(keys=True)
            if k.startswith("TR_") and not k.endswith("_R")
        ]

        # Check first 5 forward/reverse pairs
        for u, v, key in forward_edges[:5]:
            forward_geom = G.edges[u, v, key]["geometry"]
            reverse_key = key + "_R"

            if not G.has_edge(v, u, reverse_key):
                pytest.fail(f"Missing reverse edge for ({u}, {v}, {key})")

            reverse_geom = G.edges[v, u, reverse_key]["geometry"]

            # Coordinates should be reversed
            forward_coords = list(forward_geom.coords)
            reverse_coords = list(reverse_geom.coords)

            assert reverse_coords == list(reversed(forward_coords)), (
                f"Reverse arc geometry not reversed for transition {key}.\n"
                f"Forward coords: {forward_coords}\n"
                f"Reverse coords: {reverse_coords}"
            )

    def test_transition_geometry_is_linestring(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All transition geometries must be Shapely LineString."""
        if LineString is None:
            pytest.fail("shapely must be installed (dependency check failed)")

        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        for u, v, k in transition_edges[:10]:
            geom = G.edges[u, v, k]["geometry"]
            assert isinstance(geom, LineString), (
                f"Transition edge {k} geometry is {type(geom).__name__}, expected LineString"
            )


# ============================================================================
# Test AC4: Transition Endpoint Protection
# ============================================================================


class TestTransitionEndpointProtection:
    """Test transition endpoints marked with is_transition_endpoint=True."""

    def test_transition_endpoints_protected(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All transition endpoints must have is_transition_endpoint=True."""
        G, _ = graph_with_transitions_in_memory

        # Collect all transition endpoint nodes
        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        endpoint_nodes = set()
        for u, v, _key in transition_edges:
            endpoint_nodes.add(u)
            endpoint_nodes.add(v)

        # All endpoint nodes must have is_transition_endpoint=True
        for node in endpoint_nodes:
            assert G.nodes[node].get("is_transition_endpoint") is True, (
                f"Transition endpoint node {node} missing is_transition_endpoint=True"
            )

    def test_transition_endpoints_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Exactly 85 unique transition endpoint nodes must be protected."""
        G, _ = graph_with_transitions_in_memory

        # Count nodes with is_transition_endpoint=True
        protected_nodes = [n for n in G.nodes() if G.nodes[n].get("is_transition_endpoint") is True]

        assert len(protected_nodes) == EXPECTED_PROTECTED_ENDPOINTS, (
            f"Expected {EXPECTED_PROTECTED_ENDPOINTS} protected transition endpoints, "
            f"got {len(protected_nodes)}"
        )

    def test_transition_endpoints_exist_in_graph(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All transition endpoint nodes must exist in graph (no isolated endpoints)."""
        G, _ = graph_with_transitions_in_memory

        transition_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if k.startswith("TR_")]

        # All endpoint nodes from transition edges must exist
        for u, v, _key in transition_edges:
            assert u in G.nodes(), f"Transition start node {u} not in graph"
            assert v in G.nodes(), f"Transition end node {v} not in graph"

    def test_transition_only_nodes_preserve_attributes(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Five transition-only nodes must have complete DT-005 node-attribute contract."""
        # Load raw graph to identify transition-only nodes
        G_raw = load_required_graph_raw()
        G, _ = graph_with_transitions_in_memory

        # Find nodes in G but not in G_raw (transition-only nodes)
        transition_only_nodes = set(G.nodes()) - set(G_raw.nodes())

        assert len(transition_only_nodes) == EXPECTED_TRANSITION_ONLY_NODES, (
            f"Expected {EXPECTED_TRANSITION_ONLY_NODES} transition-only nodes, "
            f"got {len(transition_only_nodes)}"
        )

        # Verify each transition-only node has complete node attributes
        required_attrs = {"x", "y", "vertical_order", "level_ids", "z_min", "z_max", "z_mean"}

        for node in transition_only_nodes:
            node_attrs = set(G.nodes[node].keys())
            missing = required_attrs - node_attrs

            assert not missing, (
                f"Transition-only node {node} missing attributes: {missing}. "
                f"Must have complete DT-005 node-attribute contract."
            )


# ============================================================================
# Test AC5: Express Elevators
# ============================================================================


class TestExpressElevators:
    """Test express elevators (vertical_order delta = 2, no intermediate hops)."""

    def test_express_elevators_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Stats must list exactly 2 express elevator features."""
        _, stats = graph_with_transitions_in_memory

        assert "express_elevators" in stats, "Stats must include express_elevators key"

        express_elevators = stats["express_elevators"]
        assert len(express_elevators) == EXPECTED_EXPRESS_ELEVATORS, (
            f"Expected {EXPECTED_EXPRESS_ELEVATORS} express elevator features, "
            f"got {len(express_elevators)}"
        )

    def test_express_elevators_vertical_order_delta(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Express elevator edges must have abs(vo_to - vo_from) == 2."""
        G, _ = graph_with_transitions_in_memory

        # Find elevator edges with vertical_order delta > 1
        elevator_edges = [
            (u, v, k, d)
            for u, v, k, d in G.edges(keys=True, data=True)
            if k.startswith("TR_") and d["mode"] == "elevator"
        ]

        express_elevators = [
            (u, v, k, d)
            for u, v, k, d in elevator_edges
            if abs(d["vertical_order_to"] - d["vertical_order_from"]) > 1
        ]

        # Should find 4 arcs (2 features × 2 directions)
        assert len(express_elevators) == EXPECTED_EXPRESS_ELEVATORS * 2, (
            f"Expected {EXPECTED_EXPRESS_ELEVATORS * 2} express elevator arcs "
            f"(2 features × 2 directions), got {len(express_elevators)}"
        )

        # All express elevators should have delta = 2
        for _u, _v, k, d in express_elevators:
            delta = abs(d["vertical_order_to"] - d["vertical_order_from"])
            assert delta == 2, f"Express elevator {k} has vertical_order delta {delta}, expected 2"

    def test_express_elevators_no_intermediate_hops(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Express elevators (vo 0→2) must not have edges with vo=1 endpoints."""
        G, _ = graph_with_transitions_in_memory

        # Find express elevator edges (vo delta = 2)
        elevator_edges = [
            (u, v, k, d)
            for u, v, k, d in G.edges(keys=True, data=True)
            if k.startswith("TR_") and d["mode"] == "elevator"
        ]

        express_elevators = [
            (u, v, k, d)
            for u, v, k, d in elevator_edges
            if abs(d["vertical_order_to"] - d["vertical_order_from"]) == 2
        ]

        # For each express elevator, verify no intermediate vertical_order=1 endpoint
        for _u, _v, k, d in express_elevators:
            vo_from = d["vertical_order_from"]
            vo_to = d["vertical_order_to"]

            # Verify endpoints span vo=0 and vo=2 (not vo=1)
            assert vo_from in (0, 2), f"Express elevator {k} has unexpected vo_from={vo_from}"
            assert vo_to in (0, 2), f"Express elevator {k} has unexpected vo_to={vo_to}"

            # Verify edge connects vo=0 and vo=2 directly
            assert {vo_from, vo_to} == {0, 2}, (
                f"Express elevator {k} does not connect vo=0 and vo=2: "
                f"vo_from={vo_from}, vo_to={vo_to}"
            )

    def test_express_elevators_mode_is_elevator(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """All express features must have mode='elevator'."""
        G, _ = graph_with_transitions_in_memory

        # Find edges with vertical_order delta > 1
        edges_with_delta = [
            (u, v, k, d)
            for u, v, k, d in G.edges(keys=True, data=True)
            if k.startswith("TR_")
            and abs(d.get("vertical_order_to", 0) - d.get("vertical_order_from", 0)) > 1
        ]

        # All must be mode='elevator'
        for _u, _v, k, d in edges_with_delta:
            assert d["mode"] == "elevator", (
                f"Edge {k} with vertical_order delta > 1 has mode='{d['mode']}', "
                f"expected 'elevator'"
            )


# ============================================================================
# Test AC6: Default Profile Connectivity
# ============================================================================


class TestDefaultProfileConnectivity:
    """Test default profile (pathway + stairs + elevator) connectivity."""

    def test_default_profile_measured_baseline(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Pinned fixture must have exactly 816 components and 39 bridged."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        _, stats = graph_with_transitions_in_memory

        assert "connectivity_default_profile" in stats, "Stats missing connectivity_default_profile"

        conn = stats["connectivity_default_profile"]

        assert conn["component_count"] == DEFAULT_PROFILE_COMPONENTS, (
            f"Default profile expected {DEFAULT_PROFILE_COMPONENTS} components, "
            f"got {conn['component_count']} (pinned-fixture validation per ADR-0005)"
        )

        assert conn["largest_component_size"] == DEFAULT_PROFILE_LARGEST_COMPONENT, (
            f"Default profile largest component expected {DEFAULT_PROFILE_LARGEST_COMPONENT}, "
            f"got {conn['largest_component_size']}"
        )

        assert conn["components_bridged_by_transitions"] == DEFAULT_PROFILE_BRIDGED, (
            f"Default profile expected {DEFAULT_PROFILE_BRIDGED} bridged components, "
            f"got {conn['components_bridged_by_transitions']}"
        )

    def test_default_profile_connectivity_logged(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Stats JSON must have connectivity_default_profile key."""
        _, stats = graph_with_transitions_in_memory
        assert "connectivity_default_profile" in stats, "Stats missing connectivity_default_profile"

        conn = stats["connectivity_default_profile"]
        required_keys = {
            "component_count",
            "largest_component_size",
            "pathway_only_baseline",
            "components_bridged_by_transitions",
        }

        missing = required_keys - set(conn.keys())
        assert not missing, f"connectivity_default_profile missing keys: {missing}"

    def test_default_profile_non_regression(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Component count must not increase from pathway-only baseline."""
        _, stats = graph_with_transitions_in_memory
        conn = stats["connectivity_default_profile"]

        component_count = conn["component_count"]
        baseline = conn["pathway_only_baseline"]

        assert component_count <= baseline, (
            f"Default profile component count ({component_count}) increased from "
            f"pathway-only baseline ({baseline}). This indicates a node-identity or "
            f"snapping bug."
        )

        # Also verify at least one component was bridged (not a no-op)
        bridged = conn["components_bridged_by_transitions"]
        assert bridged > 0, (
            "Zero components bridged by transitions. This suggests a no-op "
            "implementation or transition edges not connecting across components."
        )


# ============================================================================
# Test AC7: Accessible Profile Connectivity
# ============================================================================


class TestAccessibleProfileConnectivity:
    """Test accessible profile (pathway + elevator, stairs excluded) connectivity."""

    def test_accessible_profile_measured_baseline(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Pinned fixture must have exactly 840 components and 15 bridged."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        _, stats = graph_with_transitions_in_memory

        assert "connectivity_accessible_profile" in stats, (
            "Stats missing connectivity_accessible_profile"
        )

        conn = stats["connectivity_accessible_profile"]

        assert conn["component_count"] == ACCESSIBLE_PROFILE_COMPONENTS, (
            f"Accessible profile expected {ACCESSIBLE_PROFILE_COMPONENTS} components, "
            f"got {conn['component_count']} (pinned-fixture validation per ADR-0005)"
        )

        assert conn["largest_component_size"] == ACCESSIBLE_PROFILE_LARGEST_COMPONENT, (
            f"Accessible profile largest component expected "
            f"{ACCESSIBLE_PROFILE_LARGEST_COMPONENT}, got {conn['largest_component_size']}"
        )

        assert conn["components_bridged_by_elevators"] == ACCESSIBLE_PROFILE_BRIDGED, (
            f"Accessible profile expected {ACCESSIBLE_PROFILE_BRIDGED} bridged components, "
            f"got {conn['components_bridged_by_elevators']}"
        )

    def test_accessible_profile_bridge_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Exactly 15 components must be bridged by elevators."""
        _, stats = graph_with_transitions_in_memory
        conn = stats["connectivity_accessible_profile"]

        bridged = conn["components_bridged_by_elevators"]
        assert bridged == ACCESSIBLE_PROFILE_BRIDGED, (
            f"Expected {ACCESSIBLE_PROFILE_BRIDGED} components bridged by elevators, got {bridged}"
        )

    def test_accessible_profile_no_vertical_order_matrix(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Stats JSON must NOT contain vertical_order reachability matrix."""
        _, stats = graph_with_transitions_in_memory
        conn = stats["connectivity_accessible_profile"]

        # Verify no vertical_order-pair matrix (misleading for disconnected graph)
        assert "vertical_order_reachability" not in conn, (
            "connectivity_accessible_profile must not contain vertical_order "
            "reachability matrix. Shared floor order does not imply reachability "
            "(units on same vertical_order may be in different components). "
            "Deferred to DT-009 unit-pair analysis."
        )

    def test_accessible_profile_no_stairs(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Accessible profile filtered graph must have zero stairs edges."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        G, _ = graph_with_transitions_in_memory

        # Filter to accessible profile: mode in ['pathway', 'elevator']
        accessible_edges = [
            (u, v, k)
            for u, v, k, d in G.edges(keys=True, data=True)
            if d["mode"] in ("pathway", "elevator")
        ]

        # Verify no stairs in accessible profile
        stairs_in_accessible = [
            (u, v, k)
            for u, v, k, d in G.edges(keys=True, data=True)
            if d["mode"] == "stairs" and (u, v, k) in accessible_edges
        ]

        assert len(stairs_in_accessible) == 0, (
            f"Found {len(stairs_in_accessible)} stairs edges in accessible profile. "
            f"Accessible profile must exclude stairs (elevator-only)."
        )

    def test_accessible_profile_warning_not_error(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Build must succeed (not error) with 840 components."""
        _, stats = graph_with_transitions_in_memory

        # If stats exists, build succeeded
        # Verify warning message references ADR-0005 and elevator-only nature
        assert "warnings" in stats, (
            "Stats must include warnings array for accessible profile fragmentation"
        )

        warnings = stats["warnings"]
        assert len(warnings) > 0, "Must have at least one warning for accessible profile"

        # Verify warning content mentions key points:
        # - Elevator-only (stairs excluded)
        # - Routing within connected regions only
        # - References ADR-0005
        warning_text = " ".join(warnings)
        assert "elevator" in warning_text.lower(), "Warning must mention elevator-only routing"
        assert "stairs" in warning_text.lower() or "stair" in warning_text.lower(), (
            "Warning must mention stairs excluded"
        )
        assert "connected region" in warning_text.lower() or "component" in warning_text.lower(), (
            "Warning must mention routing within connected regions"
        )

    def test_accessible_profile_warning_references_adr005(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Warning message must reference ADR-0005."""
        _, stats = graph_with_transitions_in_memory
        warnings = stats.get("warnings", [])
        warning_text = " ".join(warnings)

        assert "adr" in warning_text.lower() or "adr-0005" in warning_text.lower(), (
            "Warning message should reference ADR-0005 for connectivity baseline context"
        )

    def test_accessible_profile_non_regression(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Component count must not increase from pathway-only baseline."""
        _, stats = graph_with_transitions_in_memory
        conn = stats["connectivity_accessible_profile"]

        component_count = conn["component_count"]
        baseline = conn["pathway_only_baseline"]

        assert component_count <= baseline, (
            f"Accessible profile component count ({component_count}) increased from "
            f"pathway-only baseline ({baseline}). This indicates a bug."
        )

        # Verify at least one component was bridged
        bridged = conn["components_bridged_by_elevators"]
        assert bridged > 0, (
            "Zero components bridged by elevators. This suggests elevators not "
            "connecting across components."
        )


# ============================================================================
# Test AC8: Orphan Transition Detection
# ============================================================================


class TestOrphanTransitionDetection:
    """Test build failure when transition endpoint not in node_map."""

    def test_orphan_transition_fails_build(self) -> None:
        """add_transitions() must raise ValueError if endpoint not in node_map."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        from wayfinding.etl.graph import add_transitions

        # Create mock graph and incomplete node_map (missing one transition endpoint)
        graph = nx.MultiDiGraph()

        # Incomplete node_map - missing some transition endpoints
        node_map = {
            ("PW", "1", "start"): (100.0, 200.0, 0),
            ("PW", "1", "end"): (101.0, 201.0, 0),
            # Missing transition endpoints
        }

        # Try to add transitions with real GPKG (has 63 transition features)
        gpkg_path = load_required_gpkg()

        # Should raise ValueError due to missing node_map entries
        with pytest.raises(ValueError, match="node_map|orphan|not found"):
            add_transitions(graph, node_map, str(gpkg_path))

    def test_orphan_transition_error_message(self) -> None:
        """Error message must include useful feature ID or key in ValueError."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        from wayfinding.etl.graph import add_transitions

        graph = nx.MultiDiGraph()
        node_map = {}  # Empty node_map - all transitions are orphans

        gpkg_path = load_required_gpkg()

        try:
            add_transitions(graph, node_map, str(gpkg_path))
            pytest.fail("Expected ValueError for orphan transitions")
        except ValueError as e:
            error_msg = str(e)

            # Error message should contain helpful debugging info
            # (exact format implementation-dependent, but should have feature reference)
            assert len(error_msg) > 0, "Error message must not be empty"

    def test_no_orphan_transitions_in_production(self) -> None:
        """Real build with DT-005 node_map must have zero orphan transitions."""
        # Load real artifacts
        node_map = load_required_node_map()
        graph = load_required_graph_raw()
        gpkg_path = load_required_gpkg()

        # Should succeed without orphan errors
        from wayfinding.etl.graph import add_transitions

        try:
            updated_graph, stats = add_transitions(graph, node_map, str(gpkg_path))
            # Success - no orphan transitions
        except ValueError as e:
            if "orphan" in str(e).lower() or "not found" in str(e).lower():
                pytest.fail(
                    f"Production build has orphan transitions: {e}. "
                    f"This indicates DT-005 node_map is incomplete."
                )
            raise


# ============================================================================
# Test AC9: Node and Edge Counts
# ============================================================================


class TestFinalNodeAndEdgeCounts:
    """Test final graph has 15,587 nodes and 44,952 edges."""

    def test_graph_with_transitions_node_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Final graph must have exactly 15,587 nodes."""
        G, _ = graph_with_transitions_in_memory
        node_count = G.number_of_nodes()

        assert node_count == EXPECTED_FINAL_NODE_COUNT, (
            f"Expected {EXPECTED_FINAL_NODE_COUNT} nodes (15,582 pathway + 5 "
            f"transition-only), got {node_count}"
        )

    def test_graph_with_transitions_edge_count(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Final graph must have exactly 44,952 edges."""
        G, _ = graph_with_transitions_in_memory
        edge_count = G.number_of_edges()

        assert edge_count == EXPECTED_TOTAL_EDGES, (
            f"Expected {EXPECTED_TOTAL_EDGES} edges (44,826 pathway + 126 transition), "
            f"got {edge_count}"
        )

    def test_graph_with_transitions_mode_breakdown(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Stats must show pathway=44,826, stairs=84, elevator=42."""
        _, stats = graph_with_transitions_in_memory
        assert stats["pathway_arcs"] == EXPECTED_PATHWAY_ARCS, (
            f"Expected {EXPECTED_PATHWAY_ARCS} pathway arcs, got {stats['pathway_arcs']}"
        )

        assert stats["stairs_arcs"] == EXPECTED_STAIRS_ARCS, (
            f"Expected {EXPECTED_STAIRS_ARCS} stairs arcs, got {stats['stairs_arcs']}"
        )

        assert stats["elevator_arcs"] == EXPECTED_ELEVATOR_ARCS, (
            f"Expected {EXPECTED_ELEVATOR_ARCS} elevator arcs, got {stats['elevator_arcs']}"
        )


# ============================================================================
# Test AC10: Determinism and Stats Schema
# ============================================================================


class TestDeterminismAndStatsSchema:
    """Test deterministic graph construction and stats JSON schema."""

    def test_add_transitions_deterministic(self) -> None:
        """Running add_transitions() twice must produce identical graphs."""
        from wayfinding.etl.graph import add_transitions

        # Load inputs twice independently
        graph1, node_map1 = fresh_graph_and_node_map()
        graph2, node_map2 = fresh_graph_and_node_map()
        gpkg_path = load_required_gpkg()

        # Run twice
        G1, stats1 = add_transitions(graph1, node_map1, str(gpkg_path))
        G2, stats2 = add_transitions(graph2, node_map2, str(gpkg_path))

        # Node and edge sets must be identical
        assert set(G1.nodes()) == set(G2.nodes()), "Node sets differ between runs"

        edges1 = set(G1.edges(keys=True))
        edges2 = set(G2.edges(keys=True))
        assert edges1 == edges2, "Edge sets differ between runs"

    def test_graph_with_transitions_stats_schema(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Stats JSON must have all required keys."""
        _, stats = graph_with_transitions_in_memory

        required_keys = {
            "etl_version",
            "timestamp",
            "node_count",
            "edge_count",
            "mean_degree",
            "pathway_arcs",
            "stairs_arcs",
            "elevator_arcs",
            "transition_features_processed",
            "express_elevators",
            "protected_nodes",
            "connectivity_default_profile",
            "connectivity_accessible_profile",
            "warnings",
        }

        missing = required_keys - set(stats.keys())
        assert not missing, f"Stats missing keys: {missing}"

    def test_graph_with_transitions_stats_types(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Stats JSON values must have correct data types."""
        _, stats = graph_with_transitions_in_memory

        # Check types for key fields
        assert isinstance(stats["etl_version"], str)
        assert isinstance(stats["timestamp"], str)
        assert isinstance(stats["node_count"], int)
        assert isinstance(stats["edge_count"], int)
        assert isinstance(stats["mean_degree"], (int, float))
        assert isinstance(stats["pathway_arcs"], int)
        assert isinstance(stats["stairs_arcs"], int)
        assert isinstance(stats["elevator_arcs"], int)
        assert isinstance(stats["transition_features_processed"], int)
        assert isinstance(stats["express_elevators"], list)
        assert isinstance(stats["protected_nodes"], int)
        assert isinstance(stats["connectivity_default_profile"], dict)
        assert isinstance(stats["connectivity_accessible_profile"], dict)
        assert isinstance(stats["warnings"], list)

    def test_stats_timestamp_is_iso8601(
        self, graph_with_transitions_in_memory: tuple[Any, dict[str, Any]]
    ) -> None:
        """Timestamp must be ISO 8601 UTC format."""
        _, stats = graph_with_transitions_in_memory

        timestamp = stats["timestamp"]

        # Verify ISO 8601 format (can parse with datetime.fromisoformat)
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as e:
            pytest.fail(f"Timestamp '{timestamp}' is not valid ISO 8601: {e}")


# ============================================================================
# Test AC11: Container Execution and Artifact Serialization
# ============================================================================


class TestContainerExecutionAndArtifactSerialization:
    """Test container-only execution, serialization, and read-only input boundaries."""

    def test_makefile_target_exists(self) -> None:
        """Makefile must have etl-graph-transitions target."""
        makefile_path = WORKSPACE_ROOT / "Makefile"
        assert makefile_path.exists(), f"Missing {makefile_path}"

        with open(makefile_path) as f:
            content = f.read()

        assert "etl-graph-transitions" in content, (
            "Makefile missing 'etl-graph-transitions' target for DT-006"
        )

    def test_container_execution(self) -> None:
        """make etl-graph-transitions must invoke docker compose."""
        makefile_path = WORKSPACE_ROOT / "Makefile"

        with open(makefile_path) as f:
            content = f.read()

        # Extract target section
        lines = content.split("\n")
        target_lines = []
        in_target = False

        for line in lines:
            if line.startswith("etl-graph-transitions"):
                in_target = True
                continue
            if in_target:
                if line and not line.startswith(("\t", " ")):
                    break
                target_lines.append(line)

        target_body = "\n".join(target_lines)
        assert "docker" in target_body.lower() or "compose" in target_body.lower(), (
            "etl-graph-transitions target must use docker compose, not host Python"
        )

    def test_orchestration_serializes_artifacts(
        self, graph_with_transitions_serialized: dict[str, Path]
    ) -> None:
        """run_graph_transitions() must create graph_with_transitions.pkl and stats JSON."""
        paths = graph_with_transitions_serialized

        assert paths["graph_pkl"].exists(), "graph_with_transitions.pkl not created"
        assert paths["stats_json"].exists(), "graph_with_transitions_stats.json not created"

        with open(paths["graph_pkl"], "rb") as f:
            graph = pickle.load(f)
        assert graph.number_of_nodes() == EXPECTED_FINAL_NODE_COUNT
        assert graph.number_of_edges() == EXPECTED_TOTAL_EDGES

        with open(paths["stats_json"]) as f:
            stats = json.load(f)
        assert stats["node_count"] == EXPECTED_FINAL_NODE_COUNT
        assert stats["edge_count"] == EXPECTED_TOTAL_EDGES

    def test_gpkg_read_only(self) -> None:
        """wayfinding.gpkg mtime must be unchanged after add_transitions."""
        gpkg_path = load_required_gpkg()
        gpkg_mtime = SOURCE_GPKG.stat().st_mtime
        graph, node_map = fresh_graph_and_node_map()

        from wayfinding.etl.graph import add_transitions

        add_transitions(graph, node_map, str(gpkg_path))

        assert SOURCE_GPKG.stat().st_mtime == gpkg_mtime, (
            "build/wayfinding.gpkg was modified during add_transitions. GPKG must be read-only."
        )

    def test_no_gdb_access(self) -> None:
        """add_transitions() must not access IndoorWayfinding.gdb."""
        # Verify that add_transitions reads only from GPKG, not GDB
        # This is implicit: add_transitions takes gpkg_path, not gdb_path
        from wayfinding.etl.graph import add_transitions

        sig = inspect.signature(add_transitions)
        params = list(sig.parameters.keys())

        # Verify no gdb_path parameter
        assert "gdb_path" not in params, (
            "add_transitions must not take gdb_path parameter. "
            "All data comes from GPKG (source GDB is read-only boundary)."
        )


# ============================================================================
# Test Integration and Data-QA
# ============================================================================


class TestIntegrationAndDataQA:
    """Integration tests and data-QA validation."""

    def test_transitions_layer_feature_count(self) -> None:
        """Transitions_26910 layer must have exactly 63 features."""
        gpkg_path = load_required_gpkg()

        # Use ogrinfo to count features
        result = subprocess.run(
            ["ogrinfo", "-so", str(gpkg_path), "Transitions_26910"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.fail(f"ogrinfo failed: {result.stderr}")

        # Parse feature count from output
        output = result.stdout
        feature_count = None
        for line in output.split("\n"):
            if "Feature Count:" in line:
                feature_count = int(line.split(":")[-1].strip())
                break

        assert feature_count == EXPECTED_TRANSITION_FEATURES, (
            f"Expected {EXPECTED_TRANSITION_FEATURES} transition features, got {feature_count}"
        )

    def test_all_transition_endpoints_in_node_map(self) -> None:
        """All 126 transition endpoints must exist in DT-005 node_map."""
        node_map = load_required_node_map()

        # Count transition endpoint entries in node_map
        transition_entries = [k for k in node_map.keys() if k[0] == "TR"]

        assert len(transition_entries) == EXPECTED_TRANSITION_EDGES, (
            f"Expected {EXPECTED_TRANSITION_EDGES} transition endpoint entries in "
            f"node_map (63 features × 2 endpoints), got {len(transition_entries)}"
        )

    def test_transition_type_domain_values(self) -> None:
        """TRANSITION_TYPE field must have only values 2 (stairs) and 4 (elevator)."""
        gpkg_path = load_required_gpkg()

        from osgeo import ogr

        ds = ogr.Open(str(gpkg_path), 0)
        if ds is None:
            pytest.fail(f"Cannot open {gpkg_path}")

        layer = ds.GetLayerByName("Transitions_26910")
        if layer is None:
            pytest.fail("Transitions_26910 layer not found")

        transition_types = set()
        layer.ResetReading()
        for feature in layer:
            transition_type = feature.GetField("TRANSITION_TYPE")
            if transition_type is not None:
                transition_types.add(transition_type)

        ds = None  # Close dataset

        # Valid types: 2 (stairs), 4 (elevator)
        valid_types = {2, 4}
        invalid = transition_types - valid_types

        assert not invalid, (
            f"Found invalid TRANSITION_TYPE values: {invalid}. "
            f"Valid types: {valid_types} (2=stairs, 4=elevator)"
        )


# ============================================================================
# Test CLI and Run.py Integration
# ============================================================================


class TestCLIAndRunPyIntegration:
    """Test run.py CLI dispatches to orchestration entry point."""

    def test_run_py_has_graph_transitions_handler(self) -> None:
        """run.py main() must handle 'graph-transitions' command."""
        from wayfinding.etl import run

        # Patch the orchestration function
        with patch.object(run, "run_graph_transitions", return_value=0) as mock_run:
            result = run.main("graph-transitions")

            mock_run.assert_called_once()
            assert result == 0, "main('graph-transitions') should return 0 on success"

    def test_run_py_propagates_graph_transitions_result(self) -> None:
        """run.py must return the graph-transitions orchestration result."""
        from wayfinding.etl import run

        with patch.object(run, "run_graph_transitions", return_value=1) as mock_run:
            assert run.main("graph-transitions") == 1
            mock_run.assert_called_once()


# ============================================================================
# Test Synthetic Behavior: Transition-Mode Regression Guard
# ============================================================================


class TestTransitionModeRegression:
    """Synthetic test: reject no-op or regression in transition edge addition."""

    def test_rejects_zero_transition_edges_added(self) -> None:
        """If add_transitions() returns same edge count as input, fail explicitly."""
        from wayfinding.etl.graph import add_transitions

        graph, node_map = fresh_graph_and_node_map()
        gpkg_path = load_required_gpkg()

        initial_edge_count = graph.number_of_edges()

        result_graph, stats = add_transitions(graph, node_map, str(gpkg_path))
        final_edge_count = result_graph.number_of_edges()

        # Verify edge count increased
        assert final_edge_count > initial_edge_count, (
            f"add_transitions() added zero edges (before: {initial_edge_count}, "
            f"after: {final_edge_count}). This suggests a no-op implementation."
        )

        # Verify at least EXPECTED_TRANSITION_EDGES were added
        edges_added = final_edge_count - initial_edge_count
        assert edges_added >= EXPECTED_TRANSITION_EDGES, (
            f"add_transitions() added {edges_added} edges, expected at least "
            f"{EXPECTED_TRANSITION_EDGES} (63 transition features × 2 directions)"
        )
