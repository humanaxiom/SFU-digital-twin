"""The independent candidate audit rejects geometry and weight corruption."""

import importlib.util
import json
import pickle
from pathlib import Path

import networkx as nx
import pytest
from osgeo import ogr
from shapely.geometry import LineString


def evaluator():
    path = Path(__file__).resolve().parents[3] / "tools/evaluate_topology_candidate.py"
    spec = importlib.util.spec_from_file_location("topology_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_candidate(tmp_path):
    derived = tmp_path / "derived"
    derived.mkdir()
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(derived / "wayfinding.gpkg"))
    layer = ds.CreateLayer("Pathways_26910", geom_type=ogr.wkbLineString25D)
    layer.CreateField(ogr.FieldDefn("LENGTH_3D", ogr.OFTReal))
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetField("LENGTH_3D", 4.0)
    feature.SetGeometry(ogr.CreateGeometryFromWkt("LINESTRING Z (0 0 0, 2 0 0, 2 2 0)"))
    layer.CreateFeature(feature)
    fid = str(feature.GetFID())
    ds = None
    points = [(0, 0, 0), (2, 0, 0), (2, 2, 0)]
    graph = nx.MultiDiGraph()
    pieces = []
    for index in range(2):
        physical_id = f"{fid}:v{index}-{index + 1}"
        pieces.append({"physical_id": physical_id, "start_vertex": index,
                       "end_vertex": index + 1, "length_3d": 2.0})
        graph.add_edge(index, index + 1, feature_id=physical_id, length_3d=2.0,
                       geometry=LineString(points[index:index + 2]))
        graph.add_edge(index + 1, index, feature_id=physical_id, length_3d=2.0,
                       geometry=LineString(points[index:index + 2][::-1]))
    audit = {"features": [{"feature_id": fid, "source_length_3d": 4.0, "pieces": pieces}]}
    (derived / "topology_audit.json").write_text(json.dumps(audit))
    return graph


@pytest.mark.parametrize(
    "corruption", [None, "geometry", "weight", "missing_arc", "coordinated_source_weight"]
)
def test_source_slice_audit(tmp_path, corruption):
    graph = make_candidate(tmp_path)
    if corruption == "geometry":
        graph[0][1][0]["geometry"] = LineString([(0, 0, 0), (1, 1, 0), (2, 0, 0)])
    elif corruption == "weight":
        graph[0][1][0]["length_3d"] = 3.0
    elif corruption == "missing_arc":
        graph.remove_edge(1, 0)
    elif corruption == "coordinated_source_weight":
        audit_path = tmp_path / "derived/topology_audit.json"
        audit = json.loads(audit_path.read_text())
        audit["features"][0]["source_length_3d"] = 5.0
        for piece in audit["features"][0]["pieces"]:
            piece["length_3d"] = 2.5
        audit_path.write_text(json.dumps(audit))
        for _u, _v, data in graph.edges(data=True):
            data["length_3d"] = 2.5
    with (tmp_path / "derived/graph_raw.pkl").open("wb") as stream:
        pickle.dump(graph, stream)
    if corruption:
        with pytest.raises(
            ValueError, match="Raw piece|weight|two directed arcs|authoritative source length"
        ):
            evaluator().audit_source_slices(tmp_path)
    else:
        result = evaluator().audit_source_slices(tmp_path)
        assert result["status"] == "passed"
        assert result["physical_pieces"] == 2
