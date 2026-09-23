"""Failing tests for DT-005: Graph Node Snapping and Raw Graph Construction.

These tests check:
1. snap_nodes() function signature, precision (round-half-up to 1cm), vertical_order lookup
2. Node identity as coordinate tuples (x, y, vertical_order), not UUID or sequential int
3. build_raw_graph() creates NetworkX MultiDiGraph with bidirectional pathway edges
4. Edge attributes schema: {length_3d, mode, level_id, feature_id, geometry}
5. Reverse arc geometry is reversed coordinates: LineString(reversed(coords))
6. Self-loop detection, logging, and exclusion
7. Zero isolated nodes (degree >= 1)
8. Within-level connectivity (informational, 1-5 components per level)
9. Deterministic graph construction (same nodes/edges across runs)
10. Artifact serialization: graph_raw.pkl, node_map.pkl, graph_raw_stats.json
11. Protocol-5 pickle loadability (no nx.write_gpickle)
12. Container-only execution (no host Python, no GDB access, GPKG read-only)
13. Makefile target and CLI dispatch via run.py (not graph.py __main__)
14. Dependencies networkx>=3 and shapely>=2 declared in pyproject.toml

All tests will FAIL initially because:
- wayfinding.etl.graph module does not exist
- build/graph_raw.pkl, build/node_map.pkl, build/graph_raw_stats.json do not exist
- networkx and shapely dependencies not yet added to pyproject.toml

Tests execute inside the pinned GDAL ETL container where possible. Integration tests
use build/wayfinding.gpkg from DT-003/DT-004. Unit tests use small synthetic fixtures
to verify snapping precision, multipart handling, self-loop exclusion, and tuple node IDs.

Node map keys use layer-prefixed format (layer_prefix, feature_id, endpoint_role) to
disambiguate Pathways and Transitions FIDs which may overlap.
"""

# NetworkX documentation conventionally names graph objects G; retain that notation in tests.
# ruff: noqa: N806

import inspect
import json
import pickle
import subprocess
import tempfile
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
    from shapely.geometry import LineString, MultiLineString
except ImportError:
    LineString = None
    MultiLineString = None

# Paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
DOCKER_COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
SOURCE_GPKG = WORKSPACE_ROOT / "build" / "wayfinding.gpkg"
BUILD_DIR = WORKSPACE_ROOT / "build"
PYPROJECT_PATH = WORKSPACE_ROOT / "packages" / "wayfinding" / "pyproject.toml"

# Expected artifact paths (created by DT-005)
GRAPH_RAW_PKL = BUILD_DIR / "graph_raw.pkl"
NODE_MAP_PKL = BUILD_DIR / "node_map.pkl"
GRAPH_RAW_STATS_JSON = BUILD_DIR / "graph_raw_stats.json"

# Expected ranges from DT-005 plan §3 AC2 (rough sanity bounds)
NODE_COUNT_MIN = 10_000
NODE_COUNT_MAX = 20_000
EDGE_COUNT_MIN = 40_000  # ~22,426 pathways × 2 directions
EDGE_COUNT_MAX = 50_000

# Expected vertical_order range from data findings: [-2, 3]
VERTICAL_ORDER_MIN = -2
VERTICAL_ORDER_MAX = 3

# Snapping precision: 1 cm = 0.01 m in EPSG:26910
SNAP_PRECISION_CM = 0.01


def get_ogrinfo_json(gpkg_path: Path, layer_name: str) -> dict[str, Any]:
    """Get layer info as JSON using ogrinfo."""
    cmd = ["ogrinfo", "-json", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(f"ogrinfo failed for layer {layer_name}: {result.stderr}")

    data = json.loads(result.stdout)
    layers = data.get("layers", [])
    if not layers:
        raise ValueError(f"No layers found in ogrinfo output for {layer_name}")

    return layers[0]


# ============================================================================
# Test Dependencies and Pyproject Configuration
# ============================================================================


class TestDependencies:
    """Test that networkx and shapely dependencies are declared in pyproject.toml."""

    def test_pyproject_toml_exists(self):
        """pyproject.toml must exist in packages/wayfinding/."""
        assert PYPROJECT_PATH.exists(), f"Missing {PYPROJECT_PATH}"

    def test_networkx_dependency_declared(self):
        """pyproject.toml must declare networkx>=3.0 in dependencies."""
        import tomllib

        with open(PYPROJECT_PATH, "rb") as f:
            pyproject = tomllib.load(f)

        deps = pyproject.get("project", {}).get("dependencies", [])
        networkx_deps = [d for d in deps if "networkx" in d.lower()]

        assert len(networkx_deps) > 0, "networkx not in dependencies list"
        assert any(">=3" in d or ">= 3" in d for d in networkx_deps), (
            "networkx version must be >=3.0 (DT-005 requires MultiDiGraph)"
        )

    def test_shapely_dependency_declared(self):
        """pyproject.toml must declare shapely>=2.0 in dependencies."""
        import tomllib

        with open(PYPROJECT_PATH, "rb") as f:
            pyproject = tomllib.load(f)

        deps = pyproject.get("project", {}).get("dependencies", [])
        shapely_deps = [d for d in deps if "shapely" in d.lower()]

        assert len(shapely_deps) > 0, "shapely not in dependencies list"
        assert any(">=2" in d or ">= 2" in d for d in shapely_deps), (
            "shapely version must be >=2.0 (ADR-0004 §13 requires Shapely 2.x for pickle)"
        )


# ============================================================================
# Test Module Structure and Function Signatures
# ============================================================================


class TestGraphModuleStructure:
    """Test wayfinding.etl.graph module existence and function signatures."""

    def test_graph_module_exists(self):
        """wayfinding.etl.graph module must exist."""
        # This will fail initially with ModuleNotFoundError
        from wayfinding.etl import graph

        assert graph is not None

    def test_load_level_lookup_exists(self):
        """graph.py must define load_level_lookup() function."""
        from wayfinding.etl import graph

        assert hasattr(graph, "load_level_lookup"), (
            "graph module missing load_level_lookup function"
        )

    def test_snap_nodes_exists(self):
        """graph.py must define snap_nodes() function."""
        from wayfinding.etl import graph

        assert hasattr(graph, "snap_nodes"), "graph module missing snap_nodes function"

    def test_build_raw_graph_exists(self):
        """graph.py must define build_raw_graph() function."""
        from wayfinding.etl import graph

        assert hasattr(graph, "build_raw_graph"), "graph module missing build_raw_graph function"

    def test_snap_nodes_signature(self):
        """snap_nodes() must accept gpkg_path and level_lookup parameters."""
        from wayfinding.etl.graph import snap_nodes

        sig = inspect.signature(snap_nodes)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "snap_nodes missing gpkg_path parameter"
        assert "level_lookup" in params, "snap_nodes missing level_lookup parameter"

    def test_build_raw_graph_signature(self):
        """build_raw_graph() must accept gpkg_path, node_map, node_attrs, level_lookup."""
        from wayfinding.etl.graph import build_raw_graph

        sig = inspect.signature(build_raw_graph)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "build_raw_graph missing gpkg_path parameter"
        assert "node_map" in params, "build_raw_graph missing node_map parameter"
        assert "node_attrs" in params, "build_raw_graph missing node_attrs parameter"
        assert "level_lookup" in params, "build_raw_graph missing level_lookup parameter"


# ============================================================================
# Test Level Lookup and Vertical Order
# ============================================================================


class TestLevelLookup:
    """Test load_level_lookup() reads level_26910 table correctly."""

    @pytest.fixture
    def gpkg_path(self) -> Path:
        """Return path to build/wayfinding.gpkg (requires DT-003/DT-004)."""
        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found (requires DT-003/DT-004)")
        return SOURCE_GPKG

    def test_load_level_lookup_returns_dict(self, gpkg_path):
        """load_level_lookup() should return dict[str, int]."""
        from wayfinding.etl.graph import load_level_lookup

        level_lookup = load_level_lookup(str(gpkg_path))
        assert isinstance(level_lookup, dict), "load_level_lookup must return dict"

    def test_load_level_lookup_has_11_levels(self, gpkg_path):
        """level_lookup should have exactly 11 entries per data findings §3."""
        from wayfinding.etl.graph import load_level_lookup

        level_lookup = load_level_lookup(str(gpkg_path))
        assert len(level_lookup) == 11, f"Expected 11 levels, got {len(level_lookup)}"

    def test_load_level_lookup_vertical_order_range(self, gpkg_path):
        """vertical_order values should be in range [-2, 3]."""
        from wayfinding.etl.graph import load_level_lookup

        level_lookup = load_level_lookup(str(gpkg_path))
        vertical_orders = set(level_lookup.values())

        assert all(VERTICAL_ORDER_MIN <= v <= VERTICAL_ORDER_MAX for v in vertical_orders), (
            f"vertical_order must be in [{VERTICAL_ORDER_MIN}, {VERTICAL_ORDER_MAX}], "
            f"got {vertical_orders}"
        )

    def test_load_level_lookup_missing_layer_fails(self):
        """load_level_lookup() should raise error if level_26910 layer missing."""
        from wayfinding.etl.graph import load_level_lookup

        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Create empty GeoPackage (no level_26910 layer)
            subprocess.run(
                ["ogr2ogr", "-f", "GPKG", str(tmp_path), "/dev/null"],
                capture_output=True,
                check=False,
            )

            with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
                load_level_lookup(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)


# ============================================================================
# Test Node Snapping and Coordinate Quantization
# ============================================================================


class TestNodeSnapping:
    """Test snap_nodes() precision, vertical_order lookup, tuple node IDs."""

    def test_round_half_up_quantization(self):
        """Verify round-half-up produces correct 1cm quantization including ties."""
        # Use production helper from graph module
        from wayfinding.etl.graph import round_half_up

        # Non-tie cases
        assert round_half_up(505123.456, 2) == 505123.46
        assert round_half_up(505123.454, 2) == 505123.45
        assert round_half_up(5458789.123, 2) == 5458789.12

        # Tie cases (0.005 should round up, not banker's rounding)
        assert round_half_up(505123.455, 2) == 505123.46  # Tie: round up
        assert round_half_up(505123.445, 2) == 505123.45  # Tie: round up (to 45, not 44)
        assert round_half_up(100.005, 2) == 100.01  # Tie: round up
        assert round_half_up(100.015, 2) == 100.02  # Tie: round up

        # Negative coordinate ties
        assert round_half_up(-123.455, 2) == -123.45  # Negative tie behavior
        assert round_half_up(-123.465, 2) == -123.46

    def test_snap_nodes_returns_tuple(self):
        """snap_nodes() should return (node_map, node_attrs) tuple."""
        from wayfinding.etl.graph import snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        from wayfinding.etl.graph import load_level_lookup

        level_lookup = load_level_lookup(str(SOURCE_GPKG))

        result = snap_nodes(str(SOURCE_GPKG), level_lookup)
        assert isinstance(result, tuple), "snap_nodes must return tuple (node_map, node_attrs)"
        assert len(result) == 2, "snap_nodes must return (node_map, node_attrs)"

        node_map, node_attrs = result
        assert isinstance(node_map, dict), "node_map must be dict"
        assert isinstance(node_attrs, dict), "node_attrs must be dict"

    def test_snap_nodes_keys_are_layered_fid_role_tuples(self):
        """node_map keys must be (layer_prefix, feature_id, endpoint_role) tuples."""
        from wayfinding.etl.graph import load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)

        # Check first key
        first_key = next(iter(node_map.keys()))
        assert isinstance(first_key, tuple), "node_map keys must be tuples"
        assert len(first_key) == 3, "node_map keys must be (layer_prefix, fid, role) triples"

        layer_prefix, fid, role = first_key
        assert isinstance(layer_prefix, str), "layer_prefix must be string"
        assert layer_prefix in ("PW", "TR"), (
            f"layer_prefix must be 'PW' or 'TR', got {layer_prefix}"
        )
        assert isinstance(fid, str), "feature_id must be string"
        assert role in ("start", "end"), f"endpoint_role must be 'start' or 'end', got {role}"

    def test_snap_nodes_values_are_xyz_tuples(self):
        """node_map values must be (x, y, vertical_order) tuples with 2-decimal x/y."""
        from wayfinding.etl.graph import load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)

        first_value = next(iter(node_map.values()))
        assert isinstance(first_value, tuple), "node_map values must be tuples"
        assert len(first_value) == 3, "node_map values must be (x, y, vertical_order)"

        x, y, vo = first_value
        assert isinstance(x, float), "x must be float"
        assert isinstance(y, float), "y must be float"
        assert isinstance(vo, int), "vertical_order must be int"

        # Check 1cm precision (2 decimal places)
        assert round(x, 2) == x, f"x not rounded to 2 decimals: {x}"
        assert round(y, 2) == y, f"y not rounded to 2 decimals: {y}"

    def test_snap_nodes_vertical_order_from_level_not_z(self):
        """vertical_order must come from level_lookup, never computed from Z."""
        from wayfinding.etl.graph import load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)

        # All vertical_order values should be valid level_lookup values
        all_vo = {coord[2] for coord in node_map.values()}
        valid_vo = set(level_lookup.values())

        assert all_vo.issubset(valid_vo), (
            f"Found vertical_order values {all_vo - valid_vo} not in level_lookup {valid_vo}. "
            "vertical_order must be looked up from level_26910 table, not computed from Z."
        )

    def test_snap_nodes_covers_pathways_and_transitions(self):
        """node_map should contain endpoints from both Pathways and Transitions layers."""
        from wayfinding.etl.graph import load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)

        # Check that both PW and TR prefixes exist
        layer_prefixes = {key[0] for key in node_map.keys()}
        assert "PW" in layer_prefixes, "node_map must contain Pathways endpoints (PW prefix)"
        assert "TR" in layer_prefixes, "node_map must contain Transitions endpoints (TR prefix)"

        # Expected: ~22,426 pathways × 2 endpoints + 63 transitions × 2 endpoints
        # = ~44,852 + 126 = ~44,978 entries (assuming all distinct after snapping)
        assert len(node_map) >= 40_000, (
            f"Expected ~45k node_map entries (pathways + transitions), got {len(node_map)}"
        )

    def test_snap_nodes_deterministic(self):
        """snap_nodes() should produce identical node_map on repeated calls."""
        from wayfinding.etl.graph import load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map_1, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)
        node_map_2, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)

        assert node_map_1.keys() == node_map_2.keys(), "node_map keys differ between runs"
        assert node_map_1 == node_map_2, "node_map values differ between runs"

    def test_snap_nodes_multipart_first_last_endpoints(self):
        """For MultiLineString, start = first coord of first part, end = last of last part."""
        if LineString is None or MultiLineString is None:
            pytest.fail("shapely must be installed (dependency check failed)")

        from wayfinding.etl.graph import extract_endpoints

        # Create synthetic multipart geometry: two separate line segments
        part1 = LineString([(100.0, 200.0, 10.0), (101.0, 201.0, 10.5)])
        part2 = LineString([(105.0, 205.0, 11.0), (106.0, 206.0, 11.5)])
        multipart = MultiLineString([part1, part2])

        start_coord, end_coord = extract_endpoints(multipart)

        assert start_coord == (100.0, 200.0, 10.0)
        assert end_coord == (106.0, 206.0, 11.5)

    def test_snap_nodes_missing_level_id_fails(self):
        """snap_nodes should raise error if feature has level_id not in level_lookup."""
        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        from wayfinding.etl.graph import snap_nodes

        # Create invalid level_lookup (empty)
        invalid_level_lookup = {}

        # Should fail when trying to look up level_id
        with pytest.raises((KeyError, ValueError, RuntimeError)):
            snap_nodes(str(SOURCE_GPKG), invalid_level_lookup)

    def test_snap_nodes_empty_gpkg_layer(self):
        """snap_nodes should handle empty layer gracefully (return empty node_map)."""
        # Create temporary GPKG with empty Pathways_26910 and Transitions_26910 layers
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Create empty GeoPackage with schema but no features
            # This requires ogr2ogr or similar - for now, test the error path
            from wayfinding.etl.graph import snap_nodes

            # Non-existent GPKG should raise error
            with pytest.raises((FileNotFoundError, RuntimeError)):
                snap_nodes(str(tmp_path), {"TEST_LEVEL": 0})
        finally:
            tmp_path.unlink(missing_ok=True)


# ============================================================================
# Test Raw Graph Construction
# ============================================================================


class TestRawGraphStructure:
    """Test build_raw_graph() creates correct NetworkX MultiDiGraph."""

    @pytest.fixture
    def graph_and_stats(self):
        """Build raw graph from build/wayfinding.gpkg (integration fixture)."""
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)

        # build_raw_graph returns (G, stats)
        G, stats = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)
        return G, stats

    def test_raw_graph_is_multidirected(self, graph_and_stats):
        """Graph must be NetworkX MultiDiGraph (supports parallel edges, directed)."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        G, _ = graph_and_stats

        assert isinstance(G, nx.MultiDiGraph), f"Expected nx.MultiDiGraph, got {type(G).__name__}"

    def test_raw_graph_node_count(self, graph_and_stats):
        """Node count should be in expected range (10k-20k)."""
        G, _ = graph_and_stats
        node_count = G.number_of_nodes()

        assert NODE_COUNT_MIN < node_count < NODE_COUNT_MAX, (
            f"Expected {NODE_COUNT_MIN}-{NODE_COUNT_MAX} nodes, got {node_count}"
        )

    def test_raw_graph_edge_count(self, graph_and_stats):
        """Edge count should be ~2× pathway count (bidirectional arcs)."""
        G, _ = graph_and_stats
        edge_count = G.number_of_edges()

        assert EDGE_COUNT_MIN < edge_count < EDGE_COUNT_MAX, (
            f"Expected {EDGE_COUNT_MIN}-{EDGE_COUNT_MAX} edges, got {edge_count}"
        )

    def test_raw_graph_node_ids_are_tuples(self, graph_and_stats):
        """Node IDs must be (x, y, vertical_order) tuples, not UUID or sequential int."""
        G, _ = graph_and_stats

        # Check first 10 nodes
        for node_id in list(G.nodes())[:10]:
            assert isinstance(node_id, tuple), (
                f"Node ID must be tuple, got {type(node_id).__name__}: {node_id}"
            )
            assert len(node_id) == 3, f"Node ID must be (x, y, vo) tuple, got {node_id}"

            x, y, vo = node_id
            assert isinstance(x, float), f"x must be float, got {type(x).__name__}"
            assert isinstance(y, float), f"y must be float, got {type(y).__name__}"
            assert isinstance(vo, int), f"vertical_order must be int, got {type(vo).__name__}"

    def test_raw_graph_bidirectional(self, graph_and_stats):
        """For every (u, v, key) edge, (v, u, key+"_R") must exist."""
        G, _ = graph_and_stats

        # Sample check: verify first 100 forward edges have reverse pairs
        forward_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if not k.endswith("_R")]
        sample = forward_edges[:100]

        for u, v, key in sample:
            reverse_key = key + "_R"
            assert G.has_edge(v, u, reverse_key), (
                f"Forward edge ({u}, {v}, {key}) missing reverse arc ({v}, {u}, {reverse_key})"
            )

    def test_raw_graph_no_transition_edges(self, graph_and_stats):
        """All edges in DT-005 output must have mode='pathway' (no stairs/elevators)."""
        G, _ = graph_and_stats

        modes = {G.edges[u, v, k]["mode"] for u, v, k in G.edges(keys=True)}
        assert modes == {"pathway"}, f"Expected only mode='pathway', found modes: {modes}"


# ============================================================================
# Test Edge Attributes Schema
# ============================================================================


class TestEdgeAttributes:
    """Test edge attribute schema and completeness."""

    @pytest.fixture
    def graph_and_stats(self):
        """Build raw graph (reused fixture)."""
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)
        G, stats = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)
        return G, stats

    def test_raw_graph_edge_attributes_schema(self, graph_and_stats):
        """Every edge must have exactly 5 required attributes."""
        G, _ = graph_and_stats
        required_keys = {"length_3d", "mode", "level_id", "feature_id", "geometry"}

        # Check first 10 edges
        for u, v, k in list(G.edges(keys=True))[:10]:
            edge_attrs = set(G.edges[u, v, k].keys())
            assert edge_attrs == required_keys, (
                f"Edge ({u}, {v}, {k}) has attrs {edge_attrs}, expected {required_keys}"
            )

    def test_raw_graph_edge_mode(self, graph_and_stats):
        """All edges must have mode='pathway'."""
        G, _ = graph_and_stats

        for u, v, k in list(G.edges(keys=True))[:100]:
            mode = G.edges[u, v, k]["mode"]
            assert mode == "pathway", f"Expected mode='pathway', got '{mode}' for edge {k}"

    def test_raw_graph_edge_weights_positive(self, graph_and_stats):
        """All length_3d values must be > 0 (PHASE-1-ETL AC5)."""
        G, _ = graph_and_stats

        for u, v, k in G.edges(keys=True):
            length = G.edges[u, v, k]["length_3d"]
            assert length > 0, f"Edge ({u}, {v}, {k}) has non-positive length_3d: {length}"

    def test_raw_graph_edge_geometry_type(self, graph_and_stats):
        """All edge geometries must be Shapely LineString objects."""
        if LineString is None:
            pytest.fail("shapely must be installed (dependency check failed)")

        G, _ = graph_and_stats

        for u, v, k in list(G.edges(keys=True))[:10]:
            geom = G.edges[u, v, k]["geometry"]
            assert isinstance(geom, LineString), (
                f"Edge ({u}, {v}, {k}) geometry is {type(geom).__name__}, expected LineString"
            )

    def test_raw_graph_reverse_arc_geometry(self, graph_and_stats):
        """Reverse arc geometry must have reversed coordinates."""
        if LineString is None:
            pytest.fail("shapely must be installed (dependency check failed)")

        G, _ = graph_and_stats

        # Check first 10 forward/reverse pairs
        forward_edges = [(u, v, k) for u, v, k in G.edges(keys=True) if not k.endswith("_R")][:10]

        for u, v, key in forward_edges:
            forward_geom = G.edges[u, v, key]["geometry"]
            reverse_key = key + "_R"

            if not G.has_edge(v, u, reverse_key):
                pytest.fail(f"Missing reverse edge for ({u}, {v}, {key})")

            reverse_geom = G.edges[v, u, reverse_key]["geometry"]

            # Coordinates should be reversed
            forward_coords = list(forward_geom.coords)
            reverse_coords = list(reverse_geom.coords)

            assert reverse_coords == list(reversed(forward_coords)), (
                f"Reverse arc geometry not reversed for edge {key}.\n"
                f"Forward: {forward_coords[:3]}...{forward_coords[-3:]}\n"
                f"Reverse: {reverse_coords[:3]}...{reverse_coords[-3:]}"
            )


# ============================================================================
# Test Self-Loop Detection and Exclusion
# ============================================================================


class TestSelfLoops:
    """Test self-loop detection, logging, and exclusion (AC4)."""

    @pytest.fixture
    def graph_and_stats(self):
        """Build raw graph."""
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)
        G, stats = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)
        return G, stats

    def test_no_self_loops(self, graph_and_stats):
        """Graph must have zero self-loops (AC4 hard requirement)."""
        G, _ = graph_and_stats

        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        self_loop_count = nx.number_of_selfloops(G)
        assert self_loop_count == 0, (
            f"Found {self_loop_count} self-loops in graph. "
            "Self-loops must be excluded per DT-005 AC4."
        )

    def test_self_loop_stats_in_json(self, graph_and_stats):
        """If self-loops were found, stats JSON must record count and FIDs."""
        G, stats = graph_and_stats

        # stats should have self_loops_removed key
        assert "self_loops_removed" in stats, (
            "graph_raw_stats must include self_loops_removed count"
        )
        assert isinstance(stats["self_loops_removed"], int)

        if stats["self_loops_removed"] > 0:
            assert "self_loop_fids" in stats, (
                "If self_loops_removed > 0, must include self_loop_fids list"
            )
            assert isinstance(stats["self_loop_fids"], list)


# ============================================================================
# Test Isolated Nodes and Connectivity
# ============================================================================


class TestConnectivity:
    """Test isolated nodes (AC5) and within-level connectivity."""

    @pytest.fixture
    def graph_and_stats(self):
        """Build raw graph."""
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)
        G, stats = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)
        return G, stats

    def test_no_isolated_nodes(self, graph_and_stats):
        """All nodes in graph must have degree >= 1 (AC5 hard requirement)."""
        G, _ = graph_and_stats

        degrees = dict(G.degree())
        isolated = [node for node, deg in degrees.items() if deg == 0]

        assert len(isolated) == 0, (
            f"Found {len(isolated)} isolated nodes (degree 0). "
            f"First 5: {isolated[:5]}. All pathway endpoints must connect."
        )

    def test_within_level_connectivity(self, graph_and_stats):
        """Connectivity stats must cover every level with internally valid counts."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        G, stats = graph_and_stats

        # stats should include connectivity_by_level
        assert "connectivity_by_level" in stats, (
            "graph_raw_stats must include connectivity_by_level"
        )

        connectivity = stats["connectivity_by_level"]
        assert len(connectivity) == 11

        for level_id, level_stats in connectivity.items():
            assert set(level_stats) == {
                "node_count",
                "component_count",
                "largest_component_size",
            }
            node_count = level_stats["node_count"]
            component_count = level_stats["component_count"]
            largest_component_size = level_stats["largest_component_size"]

            assert node_count > 0, f"Level {level_id} has no pathway nodes"
            assert 1 <= component_count <= node_count
            assert 1 <= largest_component_size <= node_count


# ============================================================================
# Test Determinism and Serialization
# ============================================================================


class TestDeterminismAndSerialization:
    """Test deterministic graph construction and artifact serialization."""

    def test_build_raw_graph_deterministic(self):
        """Running build_raw_graph() twice should produce identical node/edge sets."""
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)

        G1, stats1 = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)
        G2, stats2 = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)

        # Node and edge sets must be identical
        assert set(G1.nodes()) == set(G2.nodes()), "Node sets differ between runs"

        edges1 = set(G1.edges(keys=True))
        edges2 = set(G2.edges(keys=True))
        assert edges1 == edges2, "Edge sets differ between runs"

    def test_graph_raw_stats_json_schema(self):
        """graph_raw_stats.json must have all required keys per ADR-0004 §10."""
        if not GRAPH_RAW_STATS_JSON.exists():
            pytest.skip("graph_raw_stats.json not found (run make etl-graph-raw)")

        with open(GRAPH_RAW_STATS_JSON) as f:
            stats = json.load(f)

        required_keys = {
            "etl_version",
            "timestamp",
            "node_count",
            "edge_count",
            "mean_degree",
            "self_loops_removed",
            "connectivity_by_level",
            "z_range_by_level",
        }

        missing = required_keys - set(stats.keys())
        assert not missing, f"graph_raw_stats.json missing keys: {missing}"

    def test_graph_pickle_roundtrip(self):
        """Save and load graph via pickle, assert graph structure preserved."""
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)
        G_orig, _ = build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)

        # Save and load via pickle protocol 5
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as tmp:
            tmp_path = Path(tmp.name)

        try:
            with open(tmp_path, "wb") as f:
                pickle.dump(G_orig, f, protocol=5)

            with open(tmp_path, "rb") as f:
                G_loaded = pickle.load(f)

            # Verify structure preserved
            assert G_loaded.number_of_nodes() == G_orig.number_of_nodes()
            assert G_loaded.number_of_edges() == G_orig.number_of_edges()
            assert set(G_loaded.nodes()) == set(G_orig.nodes())

        finally:
            tmp_path.unlink(missing_ok=True)

    def test_node_map_pickle_roundtrip(self):
        """node_map.pkl must be loadable via pickle protocol 5."""
        from wayfinding.etl.graph import load_level_lookup, snap_nodes

        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map_orig, _ = snap_nodes(str(SOURCE_GPKG), level_lookup)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as tmp:
            tmp_path = Path(tmp.name)

        try:
            with open(tmp_path, "wb") as f:
                pickle.dump(node_map_orig, f, protocol=5)

            with open(tmp_path, "rb") as f:
                node_map_loaded = pickle.load(f)

            assert node_map_loaded == node_map_orig, "node_map not preserved after pickle roundtrip"

        finally:
            tmp_path.unlink(missing_ok=True)


# ============================================================================
# Test Container Execution and Read-Only Boundaries
# ============================================================================


class TestContainerExecution:
    """Test container-only execution and read-only boundaries (AC7)."""

    def test_makefile_target_exists(self):
        """Makefile must have etl-graph-raw target."""
        makefile_path = WORKSPACE_ROOT / "Makefile"
        assert makefile_path.exists(), f"Missing {makefile_path}"

        with open(makefile_path) as f:
            content = f.read()

        assert "etl-graph-raw" in content, "Makefile missing 'etl-graph-raw' target for DT-005"

    def test_makefile_target_uses_docker(self):
        """make etl-graph-raw must invoke docker compose, not host Python."""
        makefile_path = WORKSPACE_ROOT / "Makefile"

        with open(makefile_path) as f:
            content = f.read()

        # Find etl-graph-raw target
        if "etl-graph-raw" not in content:
            pytest.fail("etl-graph-raw target not in Makefile")

        # Extract target section (naive: lines after 'etl-graph-raw:' until next target)
        lines = content.split("\n")
        target_lines = []
        in_target = False

        for line in lines:
            if line.startswith("etl-graph-raw"):
                in_target = True
                continue
            if in_target:
                if line and not line.startswith(("\t", " ")):
                    break
                target_lines.append(line)

        target_body = "\n".join(target_lines)
        assert "docker" in target_body.lower() or "compose" in target_body.lower(), (
            "etl-graph-raw target must use docker compose, not host Python"
        )

    def test_gpkg_read_only(self):
        """build/wayfinding.gpkg mtime must not change after graph construction."""
        if not SOURCE_GPKG.exists():
            pytest.skip("build/wayfinding.gpkg not found")

        mtime_before = SOURCE_GPKG.stat().st_mtime

        # Run graph construction (via import or CLI)
        from wayfinding.etl.graph import build_raw_graph, load_level_lookup, snap_nodes

        level_lookup = load_level_lookup(str(SOURCE_GPKG))
        node_map, node_attrs = snap_nodes(str(SOURCE_GPKG), level_lookup)
        build_raw_graph(str(SOURCE_GPKG), node_map, node_attrs, level_lookup)

        mtime_after = SOURCE_GPKG.stat().st_mtime
        assert mtime_after == mtime_before, (
            "build/wayfinding.gpkg was modified during graph construction. "
            "Graph construction must be read-only."
        )


# ============================================================================
# Test CLI and Artifact Output
# ============================================================================


class TestCLIAndArtifacts:
    """Test CLI dispatch via run.py and artifact creation."""

    def test_run_graph_raw_missing_gpkg_returns_one(self, tmp_path):
        """Graph artifact orchestration must fail cleanly without its GeoPackage input."""
        from wayfinding.etl.graph import run_graph_raw

        assert run_graph_raw(tmp_path) == 1

    def test_run_graph_raw_writes_all_artifacts(self, tmp_path):
        """Successful orchestration must serialize graph, node map, and stats."""
        if nx is None:
            pytest.fail("networkx must be installed (dependency check failed)")

        from wayfinding.etl.graph import run_graph_raw

        (tmp_path / "wayfinding.gpkg").touch()
        graph = nx.MultiDiGraph()
        graph.add_edge((1.0, 2.0, 0), (3.0, 4.0, 0), key="PW_1")
        node_map = {("PW", "1", "start"): (1.0, 2.0, 0)}
        stats = {
            "node_count": 2,
            "edge_count": 1,
            "mean_degree": 1.0,
            "self_loops_removed": 0,
        }

        with (
            patch("wayfinding.etl.graph.load_level_lookup", return_value={"LEVEL": 0}),
            patch(
                "wayfinding.etl.graph.snap_nodes",
                return_value=(node_map, {}),
            ),
            patch(
                "wayfinding.etl.graph.build_raw_graph",
                return_value=(graph, stats),
            ),
        ):
            assert run_graph_raw(tmp_path, topology_mode="endpoint-v1") == 0

        with open(tmp_path / "graph_raw.pkl", "rb") as graph_file:
            loaded_graph = pickle.load(graph_file)
        with open(tmp_path / "node_map.pkl", "rb") as node_map_file:
            loaded_node_map = pickle.load(node_map_file)
        with open(tmp_path / "graph_raw_stats.json") as stats_file:
            loaded_stats = json.load(stats_file)

        assert set(loaded_graph.edges(keys=True)) == set(graph.edges(keys=True))
        assert loaded_node_map == node_map
        assert loaded_stats == stats

    def test_run_py_accepts_graph_raw_command(self):
        """run.py must accept 'graph-raw' command for DT-005."""
        run_path = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" / "wayfinding" / "etl" / "run.py"
        )

        if not run_path.exists():
            pytest.fail("run.py module not found")

        with open(run_path) as f:
            content = f.read()

        # Check that run.py has a graph-raw command handler
        assert "graph-raw" in content or "graph_raw" in content, (
            "run.py must handle 'graph-raw' command for DT-005"
        )

    def test_makefile_etl_graph_raw_dispatches_via_run_py(self):
        """make etl-graph-raw must invoke run.py graph-raw, not graph.py directly."""
        makefile_path = WORKSPACE_ROOT / "Makefile"

        with open(makefile_path) as f:
            content = f.read()

        if "etl-graph-raw" not in content:
            pytest.fail("Makefile missing 'etl-graph-raw' target")

        # Extract target section
        lines = content.split("\n")
        target_lines = []
        in_target = False

        for line in lines:
            if line.startswith("etl-graph-raw"):
                in_target = True
                continue
            if in_target:
                if line and not line.startswith(("\t", " ")):
                    break
                target_lines.append(line)

        target_body = "\n".join(target_lines)

        # Must invoke run.py, not graph.py
        assert "wayfinding.etl.run" in target_body, (
            "etl-graph-raw must invoke wayfinding.etl.run, not graph.py __main__"
        )
        assert "graph-raw" in target_body or "graph_raw" in target_body, (
            "etl-graph-raw must pass 'graph-raw' command to run.py"
        )


# ============================================================================
# Test Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test error handling and edge cases."""

    def test_load_level_lookup_invalid_gpkg_path(self):
        """load_level_lookup should raise error for nonexistent GPKG."""
        from wayfinding.etl.graph import load_level_lookup

        with pytest.raises((FileNotFoundError, RuntimeError)):
            load_level_lookup("/nonexistent/path/to/file.gpkg")
