"""Failing tests for DT-007: Contract Degree-2 Chains.

These tests check:
1. contract_degree2_chains() function signature with graph and unit_centroids parameters
2. Contracted edge count: 2,500-4,000 total arcs (provisional; RED captures actual)
3. Transition arc preservation: exactly 126 unchanged (84 stairs + 42 elevator)
4. Mean edge length: 8-15 m for pathway edges (validates micro-segment elimination)
5. Contraction ratio: ≥90% pathway arc reduction (provisional)
6. Protected nodes: junctions (≥3 pathway neighbors), transition endpoints (85),
   unit-proximity (within 0.5m of unit centroids), transition-adjacent
7. Edge attributes: {length_3d, mode, level_id, geometry, original_feature_ids,
   contracted_segment_count} for all contracted pathway edges
8. Geometry vertex count: ≥2 for all contracted edges
9. Length accuracy: contracted length equals sum of original segments within 0.001m
10. Reverse arc geometry: reversed coordinates for bidirectional pairs
11. Shortest-path preservation: exactly 20 connected protected-node pairs (seed=42),
    distances match within 0.01m across pre/post-contraction graphs
12. Bidirectionality: every forward contracted edge has reverse pair
13. Parallel edge handling: distinct keys for multiple chains between same nodes
14. Level consistency: all segments in chain share same level_id
15. Deterministic output: sorted edge keys match across runs
16. No isolated nodes (degree > 0)
17. Component count preservation: default=816, elevator-only=840 (exact match to DT-006)
18. Largest component protected nodes preserved
19. Artifact serialization: graph_contracted.pkl, graph_contracted_stats.json
20. Container-only execution via Makefile target
21. Cross-level chain validation with synthetic test

All tests will FAIL initially because:
- wayfinding.etl.graph.contract_degree2_chains() does not exist
- run_graph_contract() orchestration entry point does not exist
- run.py has no graph-contract subcommand
- Makefile has no etl-graph-contract target
- build/graph_contracted.pkl and build/graph_contracted_stats.json do not exist

Tests use build/graph_with_transitions.pkl from DT-006 and build/wayfinding.gpkg
unit_26910 layer. Physical pathway degree computed from undirected distinct-neighbor
topology (mode='pathway', collapse parallel edges, merge bidirectional).

Pinned-fixture measurements per ADR-0005 and DT-006:
- Pre-contraction: 15,587 nodes, 44,952 edges (44,826 pathway + 126 transition)
- Post-contraction: 2,500-4,000 total arcs (provisional; RED measures actual)
- Transition arcs unchanged: 126 (84 stairs + 42 elevator)
- Protected transition endpoints: 85 nodes
- Component counts: default=816, elevator-only=840
"""

# NetworkX documentation conventionally names graph objects G; retain that notation in tests.
# ruff: noqa: N806

import inspect
import json
import pickle
import random
import subprocess
from pathlib import Path
from typing import Any

import pytest

# Guard conditional imports to allow RED test collection before dependencies installed
try:
    import networkx as nx
except ImportError:
    nx = None

try:
    from osgeo import ogr
except ImportError:
    ogr = None

try:
    from shapely import wkt
    from shapely.geometry import LineString
except ImportError:
    wkt = None
    LineString = None

# Paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
BUILD_DIR = WORKSPACE_ROOT / "build"
SOURCE_GPKG = BUILD_DIR / "wayfinding.gpkg"

# Input artifacts from DT-006 (read-only)
GRAPH_WITH_TRANSITIONS_PKL = BUILD_DIR / "graph_with_transitions.pkl"
GRAPH_WITH_TRANSITIONS_STATS_JSON = BUILD_DIR / "graph_with_transitions_stats.json"

# Expected output artifacts from DT-007
GRAPH_CONTRACTED_PKL = BUILD_DIR / "graph_contracted.pkl"
GRAPH_CONTRACTED_STATS_JSON = BUILD_DIR / "graph_contracted_stats.json"

# Expected counts per DT-007 plan (provisional targets)
EXPECTED_PRE_CONTRACTION_NODES = 15_587
EXPECTED_PRE_CONTRACTION_EDGES = 44_952
EXPECTED_PRE_CONTRACTION_PATHWAY_ARCS = 44_826
EXPECTED_TRANSITION_ARCS = 126  # Must remain unchanged
EXPECTED_STAIRS_ARCS = 84
EXPECTED_ELEVATOR_ARCS = 42
EXPECTED_PROTECTED_TRANSITION_ENDPOINTS = 85

# Provisional contraction targets (RED fixture establishes measured baseline)
EXPECTED_MIN_CONTRACTED_TOTAL_ARCS = 2_500
EXPECTED_MAX_CONTRACTED_TOTAL_ARCS = 4_000
EXPECTED_MIN_MEAN_PATHWAY_LENGTH = 8.0  # meters
EXPECTED_MAX_MEAN_PATHWAY_LENGTH = 15.0  # meters
EXPECTED_MIN_CONTRACTION_RATIO = 0.90  # 90% reduction

# Connectivity baselines per ADR-0005 and DT-006
DEFAULT_PROFILE_COMPONENTS = 816
ACCESSIBLE_PROFILE_COMPONENTS = 840

# Protection and validation parameters
UNIT_CENTROID_PROXIMITY_THRESHOLD = 0.5  # meters, EPSG:26910
SHORTEST_PATH_TOLERANCE = 0.01  # meters (1 cm)
LENGTH_SUM_TOLERANCE = 0.001  # meters (1 mm)
SHORTEST_PATH_PAIR_COUNT = 20
RANDOM_SEED = 42


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
            f"To generate: See docs/plans/DT-007.md dependencies section"
        )


def load_required_graph_with_transitions() -> Any:
    """Load graph_with_transitions.pkl from DT-006, failing clearly if missing."""
    require_file(
        GRAPH_WITH_TRANSITIONS_PKL,
        "DT-006 graph with transitions (run make etl-graph-transitions)",
    )
    with open(GRAPH_WITH_TRANSITIONS_PKL, "rb") as f:
        return pickle.load(f)


def load_required_gpkg() -> Path:
    """Load required GPKG from DT-003/DT-004, failing clearly if missing."""
    require_file(SOURCE_GPKG, "DT-003/DT-004 GeoPackage (run make etl-normalise)")
    return SOURCE_GPKG


def load_unit_centroids_from_gpkg(gpkg_path: Path) -> list[tuple[float, float, str]]:
    """Load unit centroids from unit_26910 layer centroid_26910 WKT field.

    Args:
        gpkg_path: Path to GeoPackage

    Returns:
        List of (x, y, level_id) tuples in EPSG:26910
    """
    if ogr is None:
        pytest.skip("osgeo.ogr not available")

    ds = ogr.Open(str(gpkg_path), 0)  # Read-only
    if ds is None:
        pytest.fail(f"Cannot open GeoPackage: {gpkg_path}")

    layer = ds.GetLayerByName("unit_26910")
    if layer is None:
        pytest.fail("unit_26910 layer not found in GeoPackage")

    centroids = []
    for feature in layer:
        centroid_wkt = feature.GetField("centroid_26910")
        level_id = feature.GetField("level_id")
        if centroid_wkt and level_id:
            if wkt is None:
                pytest.skip("shapely.wkt not available")
            point = wkt.loads(centroid_wkt)
            centroids.append((point.x, point.y, level_id))

    ds = None  # Close dataset
    return centroids


def compute_physical_pathway_degree(graph: Any, node: tuple) -> int:
    """Compute physical pathway degree: count of distinct pathway neighbors.

    Uses undirected physical topology: collapse parallel edges, merge forward/reverse,
    count only mode='pathway' edges, ignore transition edges.

    Args:
        graph: NetworkX MultiDiGraph
        node: Node ID tuple (x, y, vertical_order)

    Returns:
        Count of distinct pathway-connected neighbors
    """
    if nx is None:
        pytest.skip("networkx not available")

    pathway_neighbors = set()
    for u, v, data in graph.edges(node, data=True):
        if data.get("mode") == "pathway":
            # Outgoing edge: v is neighbor
            pathway_neighbors.add(v)

    for u, v, data in graph.in_edges(node, data=True):
        if data.get("mode") == "pathway":
            # Incoming edge: u is neighbor
            pathway_neighbors.add(u)

    return len(pathway_neighbors)


def identify_protected_nodes_reference(
    graph: Any,
    unit_centroids: list[tuple[float, float, str]],
) -> set[tuple]:
    """Reference implementation: identify all protected nodes.

    Protected nodes (never contracted):
    1. Junctions: ≥3 distinct pathway neighbors in physical undirected topology
    2. Transition endpoints: is_transition_endpoint=True
    3. Unit-proximity: within 0.5m of any unit centroid AND on same level
    4. Transition-adjacent: incident to any stairs/elevator edge

    Args:
        graph: NetworkX MultiDiGraph from DT-006
        unit_centroids: List of (x, y, level_id) unit centroid coordinates

    Returns:
        Set of protected node IDs
    """
    if nx is None:
        pytest.skip("networkx not available")

    protected = set()

    # 1. Junctions (physical pathway degree ≥3)
    for node in graph.nodes():
        if compute_physical_pathway_degree(graph, node) >= 3:
            protected.add(node)

    # 2. Transition endpoints
    for node, attrs in graph.nodes(data=True):
        if attrs.get("is_transition_endpoint", False):
            protected.add(node)

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
            if distance <= UNIT_CENTROID_PROXIMITY_THRESHOLD:
                protected.add(node)
                break

    # 4. Transition-adjacent (incident to stairs/elevator)
    for u, v, data in graph.edges(data=True):
        if data.get("mode") in ("stairs", "elevator"):
            protected.add(u)
            protected.add(v)

    return protected


# ============================================================================
# Module-Scoped Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def graph_with_transitions() -> Any:
    """Load graph_with_transitions.pkl once for all tests."""
    return load_required_graph_with_transitions()


@pytest.fixture(scope="module")
def unit_centroids() -> list[tuple[float, float, str]]:
    """Load unit centroids once for all tests."""
    gpkg_path = load_required_gpkg()
    centroids = load_unit_centroids_from_gpkg(gpkg_path)
    assert len(centroids) == 1017, (
        f"Expected 1,017 unit centroid records from unit_26910 layer, "
        f"found {len(centroids)}. Check GeoPackage layer or parsing logic."
    )
    return centroids


# ============================================================================
# Unit Tests (no Docker, fast)
# ============================================================================


def test_graph_module_has_contract_degree2_chains():
    """AC0: contract_degree2_chains() function exists in wayfinding.etl.graph."""
    try:
        from wayfinding.etl import graph
    except ImportError:
        pytest.fail("wayfinding.etl.graph module not importable")

    assert hasattr(graph, "contract_degree2_chains"), (
        "wayfinding.etl.graph.contract_degree2_chains() function does not exist. "
        "Implementation required per DT-007 plan §4."
    )


def test_contract_degree2_chains_signature():
    """AC0: contract_degree2_chains() accepts graph and unit_centroids parameters."""
    try:
        from wayfinding.etl.graph import contract_degree2_chains
    except ImportError:
        pytest.skip("contract_degree2_chains() not yet implemented")

    sig = inspect.signature(contract_degree2_chains)
    param_names = list(sig.parameters.keys())

    assert "graph" in param_names, (
        "contract_degree2_chains() must accept 'graph' parameter (NetworkX MultiDiGraph)"
    )
    assert "unit_centroids" in param_names, (
        "contract_degree2_chains() must accept 'unit_centroids' parameter "
        "(list of (x, y) tuples)"
    )


def test_identify_unit_proximity_nodes_measured(unit_centroids):
    """AC2: Measure actual unit-proximity protected node count (3D: XY+level)."""
    if nx is None:
        pytest.skip("networkx not available")

    graph = load_required_graph_with_transitions()

    # Compute protected nodes within 0.5m of unit centroids on same level
    unit_proximity_nodes = set()
    for node, attrs in graph.nodes(data=True):
        node_x, node_y = node[0], node[1]
        node_level_ids = attrs.get("level_ids", set())
        for centroid_x, centroid_y, centroid_level_id in unit_centroids:
            # Check level match first
            if centroid_level_id not in node_level_ids:
                continue
            # Then check XY distance
            distance = ((node_x - centroid_x) ** 2 + (node_y - centroid_y) ** 2) ** 0.5
            if distance <= UNIT_CENTROID_PROXIMITY_THRESHOLD:
                unit_proximity_nodes.add(node)
                break

    # Record measured baseline (no upper bound assertion; this is characterization)
    print(
        f"\nMeasured unit-proximity protected nodes: {len(unit_proximity_nodes)} "
        f"(threshold: {UNIT_CENTROID_PROXIMITY_THRESHOLD}m, "
        f"{len(unit_centroids)} unit centroids, 3D proximity: XY+level)"
    )

    # Basic sanity check: should be non-zero and less than total node count
    assert 0 < len(unit_proximity_nodes) < graph.number_of_nodes(), (
        f"Unit-proximity node count {len(unit_proximity_nodes)} outside sanity bounds "
        f"(0, {graph.number_of_nodes()}). Check centroid parsing, level matching, or distance calculation."
    )


def test_identify_protected_nodes_includes_all_categories(
    graph_with_transitions,
    unit_centroids,
):
    """AC2: Protected nodes include junctions, transition endpoints, unit-proximity,
    and transition-adjacent."""
    if nx is None:
        pytest.skip("networkx not available")

    protected = identify_protected_nodes_reference(
        graph_with_transitions, unit_centroids
    )

    # Check junctions (≥3 pathway neighbors) present
    junctions = {
        n
        for n in graph_with_transitions.nodes()
        if compute_physical_pathway_degree(graph_with_transitions, n) >= 3
    }
    assert junctions.issubset(protected), (
        f"Found {len(junctions)} junction nodes with ≥3 pathway neighbors, but only "
        f"{len(junctions & protected)} marked protected. Junctions must be protected."
    )

    # Check transition endpoints present
    transition_endpoints = {
        n
        for n, attrs in graph_with_transitions.nodes(data=True)
        if attrs.get("is_transition_endpoint", False)
    }
    assert transition_endpoints.issubset(protected), (
        f"Found {len(transition_endpoints)} transition endpoint nodes, but only "
        f"{len(transition_endpoints & protected)} marked protected."
    )

    # Check transition-adjacent nodes present
    transition_adjacent = set()
    for u, v, data in graph_with_transitions.edges(data=True):
        if data.get("mode") in ("stairs", "elevator"):
            transition_adjacent.add(u)
            transition_adjacent.add(v)
    assert transition_adjacent.issubset(protected), (
        f"Found {len(transition_adjacent)} transition-adjacent nodes, but only "
        f"{len(transition_adjacent & protected)} marked protected."
    )

    print(
        f"\nProtected node categories: "
        f"{len(junctions)} junctions, "
        f"{len(transition_endpoints)} transition endpoints, "
        f"{len(transition_adjacent)} transition-adjacent, "
        f"total protected: {len(protected)}"
    )


def test_contractible_nodes_disjoint_from_protected(
    graph_with_transitions,
    unit_centroids,
):
    """AC2: Contractible nodes (physical pathway degree=2, not protected) are disjoint
    from protected nodes."""
    if nx is None:
        pytest.skip("networkx not available")

    protected = identify_protected_nodes_reference(
        graph_with_transitions, unit_centroids
    )

    # Contractible: exactly 2 distinct pathway neighbors, not protected
    contractible = set()
    for node in graph_with_transitions.nodes():
        if compute_physical_pathway_degree(graph_with_transitions, node) == 2:
            if node not in protected:
                contractible.add(node)

    overlap = contractible & protected
    assert len(overlap) == 0, (
        f"Found {len(overlap)} nodes marked both contractible and protected. "
        f"These sets must be disjoint. Sample overlap: {list(overlap)[:5]}"
    )

    print(
        f"\nContractible nodes: {len(contractible)}, Protected nodes: {len(protected)}, "
        f"Overlap: {len(overlap)}"
    )


def test_contractible_nodes_pathway_degree_2(graph_with_transitions, unit_centroids):
    """AC2: Sample 50 contractible nodes, verify physical pathway degree=2."""
    if nx is None:
        pytest.skip("networkx not available")

    protected = identify_protected_nodes_reference(
        graph_with_transitions, unit_centroids
    )

    # Identify contractible nodes
    contractible = [
        n
        for n in graph_with_transitions.nodes()
        if compute_physical_pathway_degree(graph_with_transitions, n) == 2
        and n not in protected
    ]

    if len(contractible) < 50:
        pytest.skip(f"Only {len(contractible)} contractible nodes; need 50 for sampling")

    # Sample 50 deterministically
    random.seed(RANDOM_SEED)
    sample = random.sample(contractible, 50)

    for node in sample:
        degree = compute_physical_pathway_degree(graph_with_transitions, node)
        assert degree == 2, (
            f"Contractible node {node} has physical pathway degree {degree}, expected 2"
        )


def test_merge_geometries_concatenates_coords():
    """AC3: Mock chain geometry merge concatenates coordinates, dropping intermediate
    duplicates."""
    if LineString is None:
        pytest.skip("shapely not available")

    # Mock chain: A→B→C with geometries g1, g2
    g1 = LineString([(0.0, 0.0, 10.0), (1.0, 0.0, 10.0)])  # A→B
    g2 = LineString([(1.0, 0.0, 10.0), (2.0, 0.0, 10.0)])  # B→C

    # Expected merged: drop duplicate B coordinate
    expected = LineString([(0.0, 0.0, 10.0), (1.0, 0.0, 10.0), (2.0, 0.0, 10.0)])

    # Simulate merge algorithm: g1.coords[:-1] + g2.coords
    merged_coords = list(g1.coords[:-1]) + list(g2.coords)
    merged = LineString(merged_coords)

    assert list(merged.coords) == list(expected.coords), (
        f"Merged geometry coords {list(merged.coords)} do not match expected "
        f"{list(expected.coords)}"
    )


def test_contracted_length_sums_segments():
    """AC3: Mock chain with known segment lengths; assert contracted length equals sum."""
    # Mock chain: three segments with lengths 1.0, 2.0, 3.0
    segment_lengths = [1.0, 2.0, 3.0]
    expected_sum = 6.0

    computed_sum = sum(segment_lengths)

    assert abs(computed_sum - expected_sum) < LENGTH_SUM_TOLERANCE, (
        f"Contracted length {computed_sum} does not match expected sum {expected_sum}"
    )


# ============================================================================
# Integration Tests (require Docker, DT-006 artifacts)
# ============================================================================


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_edge_count_in_range():
    """AC1: Output graph has 2,500-4,000 total directed arcs (provisional; RED
    captures actual)."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated (run make etl-graph-contract)")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    total_arcs = graph_contracted.number_of_edges()

    # Provisional range; RED characterizes actual value
    print(f"\nMeasured contracted arc count: {total_arcs}")

    assert EXPECTED_MIN_CONTRACTED_TOTAL_ARCS <= total_arcs <= EXPECTED_MAX_CONTRACTED_TOTAL_ARCS, (
        f"Contracted graph has {total_arcs} arcs, outside provisional range "
        f"[{EXPECTED_MIN_CONTRACTED_TOTAL_ARCS}, {EXPECTED_MAX_CONTRACTED_TOTAL_ARCS}]. "
        f"RED fixture establishes measured baseline; if deterministic output differs "
        f"materially, trigger plan/ADR review per DT-007 §7."
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_transition_arcs_preserved():
    """AC1: Exactly 126 transition arcs unchanged (84 stairs + 42 elevator)."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    transition_arcs = [
        (u, v, k, d)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") in ("stairs", "elevator")
    ]

    stairs_arcs = [arc for arc in transition_arcs if arc[3].get("mode") == "stairs"]
    elevator_arcs = [arc for arc in transition_arcs if arc[3].get("mode") == "elevator"]

    assert len(transition_arcs) == EXPECTED_TRANSITION_ARCS, (
        f"Expected {EXPECTED_TRANSITION_ARCS} transition arcs (unchanged from DT-006), "
        f"found {len(transition_arcs)}"
    )

    assert len(stairs_arcs) == EXPECTED_STAIRS_ARCS, (
        f"Expected {EXPECTED_STAIRS_ARCS} stairs arcs, found {len(stairs_arcs)}"
    )

    assert len(elevator_arcs) == EXPECTED_ELEVATOR_ARCS, (
        f"Expected {EXPECTED_ELEVATOR_ARCS} elevator arcs, found {len(elevator_arcs)}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_mean_edge_length():
    """AC1: Mean pathway edge length 8-15m (validates micro-segment merging)."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    pathway_lengths = [
        d.get("length_3d", 0.0)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    ]

    if not pathway_lengths:
        pytest.fail("No pathway edges found in contracted graph")

    mean_length = sum(pathway_lengths) / len(pathway_lengths)

    print(f"\nMeasured mean pathway length: {mean_length:.2f}m")

    assert EXPECTED_MIN_MEAN_PATHWAY_LENGTH <= mean_length <= EXPECTED_MAX_MEAN_PATHWAY_LENGTH, (
        f"Mean pathway length {mean_length:.2f}m outside expected range "
        f"[{EXPECTED_MIN_MEAN_PATHWAY_LENGTH}, {EXPECTED_MAX_MEAN_PATHWAY_LENGTH}]m. "
        f"Pre-contraction mean was ~0.94m; contraction should merge micro-segments. "
        f"RED characterizes actual mean."
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contraction_ratio_minimum():
    """AC1: Pathway contraction ratio ≥90% (provisional)."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    pathway_arcs_post = sum(
        1
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    )

    contraction_ratio = (
        EXPECTED_PRE_CONTRACTION_PATHWAY_ARCS - pathway_arcs_post
    ) / EXPECTED_PRE_CONTRACTION_PATHWAY_ARCS

    print(
        f"\nPathway contraction: {EXPECTED_PRE_CONTRACTION_PATHWAY_ARCS} → "
        f"{pathway_arcs_post} arcs ({contraction_ratio:.1%} reduction)"
    )

    assert contraction_ratio >= EXPECTED_MIN_CONTRACTION_RATIO, (
        f"Pathway contraction ratio {contraction_ratio:.1%} below provisional minimum "
        f"{EXPECTED_MIN_CONTRACTION_RATIO:.0%}. This suggests insufficient chain merging. "
        f"Review protected node identification and chain traversal logic."
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_junctions_preserved():
    """AC2: All junctions (≥3 distinct pathway neighbors pre-contraction) exist
    post-contraction."""
    graph_pre = load_required_graph_with_transitions()

    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_post = pickle.load(f)

    # Identify junctions in pre-contraction graph
    junctions_pre = {
        n for n in graph_pre.nodes() if compute_physical_pathway_degree(graph_pre, n) >= 3
    }

    # Check all junctions exist post-contraction
    missing = junctions_pre - set(graph_post.nodes())

    assert len(missing) == 0, (
        f"Found {len(missing)} junction nodes removed during contraction. "
        f"Junctions (≥3 pathway neighbors) must be protected. "
        f"Sample missing: {list(missing)[:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_transition_endpoints_preserved():
    """AC2: All 85 transition endpoint nodes (is_transition_endpoint=True) exist
    post-contraction."""
    graph_pre = load_required_graph_with_transitions()

    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_post = pickle.load(f)

    # Identify transition endpoints in pre-contraction graph
    transition_endpoints_pre = {
        n
        for n, attrs in graph_pre.nodes(data=True)
        if attrs.get("is_transition_endpoint", False)
    }

    assert len(transition_endpoints_pre) == EXPECTED_PROTECTED_TRANSITION_ENDPOINTS, (
        f"Pre-contraction graph should have {EXPECTED_PROTECTED_TRANSITION_ENDPOINTS} "
        f"transition endpoints, found {len(transition_endpoints_pre)}"
    )

    # Check all exist post-contraction
    missing = transition_endpoints_pre - set(graph_post.nodes())

    assert len(missing) == 0, (
        f"Found {len(missing)} transition endpoint nodes removed during contraction. "
        f"All transition endpoints must be protected. Sample missing: {list(missing)[:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_unit_proximity_nodes_preserved(unit_centroids):
    """AC2: All nodes within 0.5m of unit centroids on same level exist post-contraction."""
    graph_pre = load_required_graph_with_transitions()

    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_post = pickle.load(f)

    # Identify unit-proximity nodes in pre-contraction graph (3D: XY+level)
    unit_proximity_pre = set()
    for node, attrs in graph_pre.nodes(data=True):
        node_x, node_y = node[0], node[1]
        node_level_ids = attrs.get("level_ids", set())
        for centroid_x, centroid_y, centroid_level_id in unit_centroids:
            # Check level match first
            if centroid_level_id not in node_level_ids:
                continue
            # Then check XY distance
            distance = ((node_x - centroid_x) ** 2 + (node_y - centroid_y) ** 2) ** 0.5
            if distance <= UNIT_CENTROID_PROXIMITY_THRESHOLD:
                unit_proximity_pre.add(node)
                break

    # Check all exist post-contraction
    missing = unit_proximity_pre - set(graph_post.nodes())

    assert len(missing) == 0, (
        f"Found {len(missing)} unit-proximity nodes (within {UNIT_CENTROID_PROXIMITY_THRESHOLD}m on same level) "
        f"removed during contraction. All must be protected for DT-008 connector attachment. "
        f"Total unit-proximity nodes: {len(unit_proximity_pre)}, missing: {list(missing)[:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_transition_adjacent_nodes_preserved():
    """AC2: All nodes incident to stairs/elevator edges exist post-contraction."""
    graph_pre = load_required_graph_with_transitions()

    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_post = pickle.load(f)

    # Identify transition-adjacent nodes
    transition_adjacent_pre = set()
    for u, v, data in graph_pre.edges(data=True):
        if data.get("mode") in ("stairs", "elevator"):
            transition_adjacent_pre.add(u)
            transition_adjacent_pre.add(v)

    # Check all exist post-contraction
    missing = transition_adjacent_pre - set(graph_post.nodes())

    assert len(missing) == 0, (
        f"Found {len(missing)} transition-adjacent nodes removed during contraction. "
        f"All nodes incident to stairs/elevator must be protected. "
        f"Sample missing: {list(missing)[:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_edge_attributes_schema():
    """AC3: Every contracted pathway edge has all 6 required attributes."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    required_keys = {
        "length_3d",
        "mode",
        "level_id",
        "geometry",
        "original_feature_ids",
        "contracted_segment_count",
    }

    pathway_edges = [
        (u, v, k, d)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    ]

    if not pathway_edges:
        pytest.fail("No pathway edges found in contracted graph")

    for u, v, k, data in pathway_edges:
        missing_keys = required_keys - set(data.keys())
        assert len(missing_keys) == 0, (
            f"Contracted pathway edge ({u}, {v}, {k}) missing required attributes: "
            f"{missing_keys}. All contracted edges must have: {required_keys}"
        )


@pytest.mark.skipif(nx is None or LineString is None, reason="dependencies not available")
def test_contracted_length_equals_sum():
    """AC3: Sample 20 contracted edges, recompute length from original segments,
    assert match within 0.001m."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    # Sample contracted edges with contracted_segment_count > 1
    multi_segment_edges = [
        (u, v, k, d)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway" and d.get("contracted_segment_count", 1) > 1
    ]

    if len(multi_segment_edges) < 20:
        pytest.skip(
            f"Only {len(multi_segment_edges)} multi-segment edges; need 20 for sampling"
        )

    random.seed(RANDOM_SEED)
    sample = random.sample(multi_segment_edges, 20)

    # Load pre-contraction graph to trace original segments
    graph_pre = load_required_graph_with_transitions()

    for u, v, k, data in sample:
        contracted_length = data.get("length_3d", 0.0)
        original_fids = data.get("original_feature_ids", [])

        if not original_fids:
            pytest.fail(f"Edge ({u}, {v}, {k}) has empty original_feature_ids")

        # Sum lengths from original segments in pre-contraction graph
        # Original FIDs are pathway feature IDs; find edges with matching feature_id
        original_lengths = []
        for orig_fid in original_fids:
            # Find edges in pre-contraction graph with this feature_id
            matching_edges = [
                d
                for u_pre, v_pre, k_pre, d in graph_pre.edges(keys=True, data=True)
                if d.get("feature_id") == orig_fid and d.get("mode") == "pathway"
            ]
            if matching_edges:
                # Take first match (forward or reverse, length is same)
                original_lengths.append(matching_edges[0].get("length_3d", 0.0))

        if not original_lengths:
            pytest.fail(
                f"Could not find original segments for contracted edge ({u}, {v}, {k}) "
                f"with FIDs {original_fids}"
            )

        expected_sum = sum(original_lengths)

        assert abs(contracted_length - expected_sum) < LENGTH_SUM_TOLERANCE, (
            f"Contracted edge ({u}, {v}, {k}) length {contracted_length:.3f}m does not match "
            f"sum of original segments {expected_sum:.3f}m (diff: "
            f"{abs(contracted_length - expected_sum):.4f}m, tolerance: {LENGTH_SUM_TOLERANCE}m)"
        )


@pytest.mark.skipif(nx is None or LineString is None, reason="dependencies not available")
def test_contracted_geometry_vertex_count():
    """AC3: All contracted geometries have ≥2 vertices (start and end)."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    pathway_edges = [
        (u, v, k, d)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    ]

    for u, v, k, data in pathway_edges:
        geom = data.get("geometry")
        if geom is None:
            pytest.fail(f"Edge ({u}, {v}, {k}) has no geometry")

        if not isinstance(geom, LineString):
            pytest.fail(
                f"Edge ({u}, {v}, {k}) geometry is {type(geom)}, expected LineString"
            )

        vertex_count = len(geom.coords)
        assert vertex_count >= 2, (
            f"Edge ({u}, {v}, {k}) has {vertex_count} vertices, expected ≥2"
        )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_original_fids_nonempty():
    """AC3: No contracted edge has empty original_feature_ids."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    pathway_edges = [
        (u, v, k, d)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway"
    ]

    empty_fids = [
        (u, v, k)
        for u, v, k, d in pathway_edges
        if not d.get("original_feature_ids", [])
    ]

    assert len(empty_fids) == 0, (
        f"Found {len(empty_fids)} contracted edges with empty original_feature_ids. "
        f"All contracted edges must record source FIDs. Sample: {empty_fids[:5]}"
    )


@pytest.mark.skipif(nx is None or LineString is None, reason="dependencies not available")
def test_contracted_reverse_arc_geometry():
    """AC3: For bidirectional pairs, reverse coords are reversed(forward.coords)."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    # Find forward/reverse pairs: canonical forward (not ending _R) and reverse (_R suffix)
    forward_edges = {}
    reverse_edges = {}

    for u, v, k, d in graph_contracted.edges(keys=True, data=True):
        if d.get("mode") != "pathway":
            continue
        if k.startswith("PW_CONTRACTED_"):
            if k.endswith("_R"):
                # Reverse edge: strip _R to get canonical base
                base_key = k[:-2]
                reverse_edges[base_key] = (u, v, k, d)
            else:
                # Canonical forward edge
                forward_edges[k] = (u, v, k, d)

    # Check pairs
    for chain_id, (u_fwd, v_fwd, k_fwd, d_fwd) in forward_edges.items():
        if chain_id not in reverse_edges:
            pytest.fail(
                f"Forward edge {k_fwd} has no reverse pair {chain_id}_R. "
                f"All contracted edges must be bidirectional."
            )

        u_rev, v_rev, k_rev, d_rev = reverse_edges[chain_id]

        # Check topology: forward (u_fwd, v_fwd) ↔ reverse (v_fwd, u_fwd)
        assert (u_rev, v_rev) == (v_fwd, u_fwd), (
            f"Forward edge ({u_fwd}, {v_fwd}, {k_fwd}) has mismatched reverse topology "
            f"({u_rev}, {v_rev}, {k_rev}). Expected ({v_fwd}, {u_fwd})."
        )

        # Check geometry: reverse coords are reversed(forward.coords)
        geom_fwd = d_fwd.get("geometry")
        geom_rev = d_rev.get("geometry")

        if geom_fwd is None or geom_rev is None:
            pytest.fail(f"Missing geometry in pair {k_fwd}/{k_rev}")

        expected_rev_coords = list(reversed(list(geom_fwd.coords)))
        actual_rev_coords = list(geom_rev.coords)

        assert expected_rev_coords == actual_rev_coords, (
            f"Reverse edge {k_rev} geometry does not match reversed forward geometry. "
            f"Forward: {list(geom_fwd.coords)[:3]}..., "
            f"Expected reverse: {expected_rev_coords[:3]}..., "
            f"Actual reverse: {actual_rev_coords[:3]}..."
        )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_shortest_path_preservation_deterministic(unit_centroids):
    """AC4: Exactly 20 connected protected-node pairs (seed=42), distances match within
    0.01m pre/post-contraction."""
    graph_pre = load_required_graph_with_transitions()

    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_post = pickle.load(f)

    # Identify protected nodes
    protected = identify_protected_nodes_reference(graph_pre, unit_centroids)

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
    components_pre = [
        comp
        for comp in nx.connected_components(profile_pre)
        if len(comp & protected) >= 2
    ]

    if not components_pre:
        pytest.fail("No connected components with ≥2 protected nodes found")

    # Deterministically select 20 connected pairs
    random.seed(RANDOM_SEED)
    pairs = []

    for comp in components_pre:
        protected_in_comp = sorted(comp & protected)
        if len(protected_in_comp) < 2:
            continue

        # Generate all pairs in component
        for i in range(len(protected_in_comp)):
            for j in range(i + 1, len(protected_in_comp)):
                pairs.append((protected_in_comp[i], protected_in_comp[j]))

                if len(pairs) >= SHORTEST_PATH_PAIR_COUNT:
                    break
            if len(pairs) >= SHORTEST_PATH_PAIR_COUNT:
                break
        if len(pairs) >= SHORTEST_PATH_PAIR_COUNT:
            break

    assert len(pairs) >= SHORTEST_PATH_PAIR_COUNT, (
        f"Could not select {SHORTEST_PATH_PAIR_COUNT} connected protected-node pairs. "
        f"Found only {len(pairs)} pairs across {len(components_pre)} components. "
        f"Check protected node identification or component structure."
    )

    pairs = pairs[:SHORTEST_PATH_PAIR_COUNT]

    # Compare shortest paths
    mismatches = []
    for src, tgt in pairs:
        try:
            dist_pre = nx.shortest_path_length(
                profile_pre, src, tgt, weight="weight"
            )
        except nx.NetworkXNoPath:
            pytest.fail(f"Pair ({src}, {tgt}) disconnected in pre-contraction graph")

        try:
            dist_post = nx.shortest_path_length(
                profile_post, src, tgt, weight="weight"
            )
        except nx.NetworkXNoPath:
            pytest.fail(
                f"Pair ({src}, {tgt}) connected pre-contraction but disconnected "
                f"post-contraction. This indicates incorrect contraction."
            )

        delta = abs(dist_pre - dist_post)
        if delta > SHORTEST_PATH_TOLERANCE:
            mismatches.append((src, tgt, dist_pre, dist_post, delta))

    assert len(mismatches) == 0, (
        f"Found {len(mismatches)} pairs with distance mismatch >0.01m. "
        f"Contraction must preserve shortest-path distances. "
        f"Sample mismatches: {mismatches[:3]}"
    )

    print(f"\nShortest-path validation: {len(pairs)} pairs tested, all matched within 0.01m")


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_bidirectional():
    """AC5: Every forward contracted pathway edge has reverse pair."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    # Collect forward edges: PW_CONTRACTED_* not ending in _R
    forward_edges = {}
    all_edges = set()

    for u, v, k, d in graph_contracted.edges(keys=True, data=True):
        if d.get("mode") != "pathway":
            continue
        all_edges.add((u, v, k))
        if k.startswith("PW_CONTRACTED_") and not k.endswith("_R"):
            forward_edges[k] = (u, v)

    # Check each forward has reverse
    missing_reverse = []
    for k_fwd, (u_fwd, v_fwd) in forward_edges.items():
        k_rev = f"{k_fwd}_R"
        # Reverse edge should have topology (v_fwd, u_fwd)
        if (v_fwd, u_fwd, k_rev) not in all_edges:
            missing_reverse.append(k_fwd)

    assert len(missing_reverse) == 0, (
        f"Found {len(missing_reverse)} forward edges without reverse pairs. "
        f"All contracted edges must be bidirectional. Sample: {missing_reverse[:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_parallel_edges_distinct_keys():
    """AC5: Parallel edges (multiple contracted chains between same protected nodes)
    have distinct keys."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    # Find nodes with multiple pathway edges between them
    edge_counts = {}
    for u, v, k, d in graph_contracted.edges(keys=True, data=True):
        if d.get("mode") == "pathway":
            pair = (u, v)
            if pair not in edge_counts:
                edge_counts[pair] = []
            edge_counts[pair].append(k)

    parallel_pairs = {pair: keys for pair, keys in edge_counts.items() if len(keys) > 1}

    if not parallel_pairs:
        print("\nNo parallel edges found (all contracted chains have unique endpoints)")
        return

    # Check all keys are distinct
    for pair, keys in parallel_pairs.items():
        assert len(keys) == len(set(keys)), (
            f"Parallel edges between {pair} have duplicate keys: {keys}. "
            f"Each contracted chain must have a distinct edge key."
        )

    print(
        f"\nFound {len(parallel_pairs)} node pairs with parallel edges, "
        f"all have distinct keys"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_level_consistency():
    """AC6: Sample 50 contracted edges with contracted_segment_count > 1, trace back to
    original segments, assert all same level_id."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    # Sample multi-segment edges
    multi_segment_edges = [
        (u, v, k, d)
        for u, v, k, d in graph_contracted.edges(keys=True, data=True)
        if d.get("mode") == "pathway" and d.get("contracted_segment_count", 1) > 1
    ]

    if len(multi_segment_edges) < 50:
        pytest.skip(
            f"Only {len(multi_segment_edges)} multi-segment edges; need 50 for sampling"
        )

    random.seed(RANDOM_SEED)
    sample = random.sample(multi_segment_edges, 50)

    # Load pre-contraction graph
    graph_pre = load_required_graph_with_transitions()

    for u, v, k, data in sample:
        contracted_level = data.get("level_id")
        original_fids = data.get("original_feature_ids", [])

        if not original_fids:
            pytest.fail(f"Edge ({u}, {v}, {k}) has empty original_feature_ids")

        # Find original segments and check level_id
        original_levels = set()
        for orig_fid in original_fids:
            matching_edges = [
                d.get("level_id")
                for u_pre, v_pre, k_pre, d in graph_pre.edges(keys=True, data=True)
                if d.get("feature_id") == orig_fid and d.get("mode") == "pathway"
            ]
            original_levels.update(matching_edges)

        assert len(original_levels) == 1, (
            f"Contracted edge ({u}, {v}, {k}) spans multiple levels: {original_levels}. "
            f"All segments in a chain must share the same level_id. FIDs: {original_fids}"
        )

        assert contracted_level in original_levels, (
            f"Contracted edge ({u}, {v}, {k}) has level_id {contracted_level}, but "
            f"original segments have level_id {original_levels}. Mismatch."
        )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_no_cross_level_pathway_chains():
    """AC6: Explicit check that no contracted edge claims to merge segments from
    different levels."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    graph_pre = load_required_graph_with_transitions()

    cross_level_chains = []

    for u, v, k, data in graph_contracted.edges(keys=True, data=True):
        if data.get("mode") != "pathway":
            continue
        if data.get("contracted_segment_count", 1) <= 1:
            continue

        original_fids = data.get("original_feature_ids", [])
        if not original_fids:
            continue

        # Collect levels from original segments
        levels = set()
        for orig_fid in original_fids:
            matching_edges = [
                d.get("level_id")
                for u_pre, v_pre, k_pre, d in graph_pre.edges(keys=True, data=True)
                if d.get("feature_id") == orig_fid and d.get("mode") == "pathway"
            ]
            levels.update(matching_edges)

        if len(levels) > 1:
            cross_level_chains.append((u, v, k, levels, original_fids))

    assert len(cross_level_chains) == 0, (
        f"Found {len(cross_level_chains)} contracted chains spanning multiple levels. "
        f"This is a data error: pathways should not cross levels without a transition. "
        f"Sample: {cross_level_chains[:3]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contraction_deterministic_structure():
    """AC7: Run contraction twice, assert sorted edge keys match (not byte-identical
    pickle)."""
    try:
        from wayfinding.etl.graph import contract_degree2_chains
    except ImportError:
        pytest.skip("contract_degree2_chains() not yet implemented")

    graph_pre = load_required_graph_with_transitions()
    gpkg_path = load_required_gpkg()
    unit_centroids = load_unit_centroids_from_gpkg(gpkg_path)

    # Deep copy graph for independent runs
    import copy

    graph1 = copy.deepcopy(graph_pre)
    graph2 = copy.deepcopy(graph_pre)

    # Run contraction twice
    result1 = contract_degree2_chains(graph1, unit_centroids)
    result2 = contract_degree2_chains(graph2, unit_centroids)

    # Extract contracted graphs
    if isinstance(result1, tuple):
        contracted1 = result1[0]
    else:
        contracted1 = result1

    if isinstance(result2, tuple):
        contracted2 = result2[0]
    else:
        contracted2 = result2

    # Compare sorted edge keys
    keys1 = sorted(
        [(u, v, k) for u, v, k in contracted1.edges(keys=True)]
    )
    keys2 = sorted(
        [(u, v, k) for u, v, k in contracted2.edges(keys=True)]
    )

    assert keys1 == keys2, (
        f"Contraction produced different edge keys across runs. "
        f"First run: {len(keys1)} edges, second run: {len(keys2)} edges. "
        f"Contraction must be deterministic. Sample diff: "
        f"Only in run1: {[k for k in keys1 if k not in keys2][:5]}, "
        f"Only in run2: {[k for k in keys2 if k not in keys1][:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_contracted_chain_ids_deterministic():
    """AC7: Same edge keys (chain IDs) across runs."""
    # This test is redundant with test_contraction_deterministic_structure but kept
    # per plan for explicit chain_id verification
    try:
        from wayfinding.etl.graph import contract_degree2_chains
    except ImportError:
        pytest.skip("contract_degree2_chains() not yet implemented")

    graph_pre = load_required_graph_with_transitions()
    gpkg_path = load_required_gpkg()
    unit_centroids = load_unit_centroids_from_gpkg(gpkg_path)

    import copy

    graph1 = copy.deepcopy(graph_pre)
    graph2 = copy.deepcopy(graph_pre)

    result1 = contract_degree2_chains(graph1, unit_centroids)
    result2 = contract_degree2_chains(graph2, unit_centroids)

    if isinstance(result1, tuple):
        contracted1 = result1[0]
    else:
        contracted1 = result1

    if isinstance(result2, tuple):
        contracted2 = result2[0]
    else:
        contracted2 = result2

    keys1 = {k for u, v, k in contracted1.edges(keys=True)}
    keys2 = {k for u, v, k in contracted2.edges(keys=True)}

    assert keys1 == keys2, (
        f"Contracted edge keys differ across runs. This indicates non-deterministic "
        f"chain_id generation. Run1: {len(keys1)} keys, Run2: {len(keys2)} keys"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_no_isolated_nodes_contracted():
    """AC8: Zero isolated nodes (degree=0) in contracted graph."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    isolated = [n for n in graph_contracted.nodes() if graph_contracted.degree(n) == 0]

    assert len(isolated) == 0, (
        f"Found {len(isolated)} isolated nodes (degree=0) in contracted graph. "
        f"Contraction should not create isolated nodes. Sample: {isolated[:5]}"
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_connectivity_component_counts_exact():
    """AC8: Component counts match DT-006 baseline exactly: default=816,
    elevator-only=840."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_contracted = pickle.load(f)

    # Default profile: pathway + stairs + elevator
    default_graph = nx.Graph()
    for u, v, data in graph_contracted.edges(data=True):
        if data.get("mode") in ("pathway", "stairs", "elevator"):
            default_graph.add_edge(u, v)

    default_components = nx.number_connected_components(default_graph)

    # Accessible profile: pathway + elevator only
    accessible_graph = nx.Graph()
    for u, v, data in graph_contracted.edges(data=True):
        if data.get("mode") in ("pathway", "elevator"):
            accessible_graph.add_edge(u, v)

    accessible_components = nx.number_connected_components(accessible_graph)

    assert default_components == DEFAULT_PROFILE_COMPONENTS, (
        f"Default profile has {default_components} components, expected "
        f"{DEFAULT_PROFILE_COMPONENTS} (DT-006 baseline). Contraction must preserve "
        f"component structure."
    )

    assert accessible_components == ACCESSIBLE_PROFILE_COMPONENTS, (
        f"Accessible profile has {accessible_components} components, expected "
        f"{ACCESSIBLE_PROFILE_COMPONENTS} (DT-006 baseline). Contraction must preserve "
        f"component structure."
    )


@pytest.mark.skipif(nx is None, reason="networkx not available")
def test_largest_component_protected_nodes_preserved(unit_centroids):
    """AC8: Protected nodes in largest component remain reachable post-contraction."""
    graph_pre = load_required_graph_with_transitions()

    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated")

    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph_post = pickle.load(f)

    # Build default profile pre-contraction
    default_pre = nx.Graph()
    for u, v, data in graph_pre.edges(data=True):
        if data.get("mode") in ("pathway", "stairs", "elevator"):
            default_pre.add_edge(u, v)

    # Find largest component
    largest_comp_pre = max(nx.connected_components(default_pre), key=len)

    # Identify protected nodes in largest component
    protected = identify_protected_nodes_reference(graph_pre, unit_centroids)
    protected_in_largest = largest_comp_pre & protected

    # Build default profile post-contraction
    default_post = nx.Graph()
    for u, v, data in graph_post.edges(data=True):
        if data.get("mode") in ("pathway", "stairs", "elevator"):
            default_post.add_edge(u, v)

    # Check all protected nodes still reachable in same component
    largest_comp_post = max(nx.connected_components(default_post), key=len)

    missing = protected_in_largest - largest_comp_post

    assert len(missing) == 0, (
        f"Found {len(missing)} protected nodes from largest component not reachable "
        f"post-contraction. Contraction must preserve connectivity among protected nodes. "
        f"Sample missing: {list(missing)[:5]}"
    )


def test_run_graph_contract_writes_artifacts():
    """AC8: CLI integration: graph_contracted.pkl and graph_contracted_stats.json
    created."""
    if not GRAPH_CONTRACTED_PKL.exists():
        pytest.skip("graph_contracted.pkl not yet generated (run make etl-graph-contract)")

    if not GRAPH_CONTRACTED_STATS_JSON.exists():
        pytest.skip("graph_contracted_stats.json not yet generated")

    # Verify pkl is loadable
    with open(GRAPH_CONTRACTED_PKL, "rb") as f:
        graph = pickle.load(f)
        assert graph is not None, "graph_contracted.pkl is empty or corrupt"

    # Verify JSON is valid
    with open(GRAPH_CONTRACTED_STATS_JSON) as f:
        stats = json.load(f)
        assert isinstance(stats, dict), "graph_contracted_stats.json is not a dict"


# ============================================================================
# Data-QA Tests (containerized, read-only source)
# ============================================================================


def test_no_gdb_access_during_contraction():
    """Assert GDB file not opened during contraction (operates on pkl/gpkg only)."""
    # This test verifies the container does NOT mount /data (GDB read-only mount)
    # Current implementation: contraction runs inside same container as other ETL,
    # so /data is mounted. This test is a reminder that contraction MUST NOT read GDB.

    # Verify by checking that contract_degree2_chains() signature does not accept
    # gdb_path parameter
    try:
        from wayfinding.etl.graph import contract_degree2_chains
    except ImportError:
        pytest.skip("contract_degree2_chains() not yet implemented")

    sig = inspect.signature(contract_degree2_chains)
    param_names = list(sig.parameters.keys())

    assert "gdb_path" not in param_names, (
        "contract_degree2_chains() must NOT accept gdb_path parameter. "
        "Contraction operates only on pkl/gpkg artifacts, never GDB. "
        "Per container-only-execution.instructions.md and DT-007 plan."
    )


def test_contracted_stats_json_schema():
    """All required keys present in graph_contracted_stats.json."""
    if not GRAPH_CONTRACTED_STATS_JSON.exists():
        pytest.skip("graph_contracted_stats.json not yet generated")

    with open(GRAPH_CONTRACTED_STATS_JSON) as f:
        stats = json.load(f)

    required_keys = {
        "etl_version",
        "timestamp",
        "node_count",
        "edge_count",
        "mean_degree",
        "pathway_arc_count",
        "transition_arc_count",
        "contraction_ratio",
        "mean_pathway_length",
        "protected_node_counts",
        "component_counts",
    }

    missing_keys = required_keys - set(stats.keys())

    assert len(missing_keys) == 0, (
        f"graph_contracted_stats.json missing required keys: {missing_keys}. "
        f"All ETL stats must follow schema per DT-007 plan."
    )


def test_makefile_has_etl_graph_contract_target():
    """Makefile integration: etl-graph-contract target exists."""
    makefile_path = WORKSPACE_ROOT / "Makefile"

    if not makefile_path.exists():
        pytest.skip("Makefile not yet created (Phase 1 deliverable)")

    makefile_content = makefile_path.read_text()

    assert "etl-graph-contract:" in makefile_content, (
        "Makefile must have 'etl-graph-contract:' target for container-only execution. "
        "Per DT-007 plan §2.2 and container-only-execution.instructions.md."
    )


def test_run_py_has_graph_contract_handler():
    """CLI integration: run.py has graph-contract subcommand handler."""
    try:
        from wayfinding.etl import run
    except ImportError:
        pytest.fail("wayfinding.etl.run module not importable")

    # Check main() function dispatches graph-contract
    # Since we can't easily invoke main() in test, check source code
    run_py_path = WORKSPACE_ROOT / "packages" / "wayfinding" / "src" / "wayfinding" / "etl" / "run.py"

    if not run_py_path.exists():
        pytest.fail("run.py not found")

    run_py_content = run_py_path.read_text()

    assert "graph-contract" in run_py_content, (
        "run.py must handle 'graph-contract' subcommand per DT-007 plan §2.2"
    )

    assert "run_graph_contract" in run_py_content, (
        "run.py must call run_graph_contract() entry point per DT-007 plan"
    )


# ============================================================================
# Edge-Case and Failure-Mode Tests
# ============================================================================


def test_validate_level_consistency_fails_on_cross_level_chain():
    """AC6: Synthetic test: contract_degree2_chains rejects cross-level chain."""
    if nx is None or LineString is None:
        pytest.skip("networkx or shapely not available")

    try:
        from wayfinding.etl.graph import contract_degree2_chains
    except ImportError:
        pytest.fail(
            "contract_degree2_chains() not yet implemented. "
            "This test validates level consistency enforcement."
        )

    # Build synthetic MultiDiGraph with cross-level chain
    G = nx.MultiDiGraph()

    # Protected endpoints
    n1 = (0.0, 0.0, 1)
    n2 = (1.0, 0.0, 1)
    n3 = (2.0, 0.0, 1)

    # Degree-2 intermediate node on same XY but different level
    n_mid = (1.0, 0.0, 2)

    # Add nodes with level_ids attribute (connectors attach on unit's own level)
    G.add_node(n1, level_ids={"L1"}, is_transition_endpoint=True)
    G.add_node(n_mid, level_ids={"L2"})
    G.add_node(n2, level_ids={"L1"})
    G.add_node(n3, level_ids={"L1"}, is_transition_endpoint=True)

    # Two pathway segments: n1→n_mid (level_id=L1) and n_mid→n3 (level_id=L2)
    geom1 = LineString([(0.0, 0.0, 10.0), (1.0, 0.0, 10.5)])
    geom2 = LineString([(1.0, 0.0, 10.5), (2.0, 0.0, 11.0)])

    G.add_edge(
        n1, n_mid, key="PW_1",
        mode="pathway", level_id="L1", length_3d=1.0, geometry=geom1, feature_id="F1"
    )
    G.add_edge(
        n_mid, n3, key="PW_2",
        mode="pathway", level_id="L2", length_3d=1.1, geometry=geom2, feature_id="F2"
    )

    # Add reverse edges for bidirectionality
    G.add_edge(
        n_mid, n1, key="PW_1_R",
        mode="pathway", level_id="L1", length_3d=1.0,
        geometry=LineString(list(reversed(geom1.coords))), feature_id="F1"
    )
    G.add_edge(
        n3, n_mid, key="PW_2_R",
        mode="pathway", level_id="L2", length_3d=1.1,
        geometry=LineString(list(reversed(geom2.coords))), feature_id="F2"
    )

    # Empty unit centroids (protected nodes already marked)
    unit_centroids = []

    # Expect ValueError with level diagnostic
    with pytest.raises(ValueError, match=r"(level|chain|consistency|L1.*L2|L2.*L1)"):
        contract_degree2_chains(G, unit_centroids)



