"""DT-036: exact OGR floor filtering must avoid unrelated Python features."""

import json

import pytest
from osgeo import ogr

from wayfinding.demo.artifact import ArtifactRepository, ArtifactUnavailableError


class CountingLayer:
    """Observe real OGR iteration while forwarding real SQL filter behavior."""

    def __init__(self, layer):
        self.layer = layer
        self.visited = []

    def __getattr__(self, name):
        return getattr(self.layer, name)

    def __iter__(self):
        for feature in self.layer:
            self.visited.append(feature.GetField("detail_id"))
            yield feature


class CountingDataset:
    def __init__(self, dataset):
        self.dataset = dataset
        self.layer = CountingLayer(dataset.GetLayerByName("detail_26910"))

    def GetLayerByName(self, name):  # noqa: N802 - real OGR interface
        assert name == "detail_26910"
        return self.layer


@pytest.mark.parametrize("level_id", ["FLOOR_1", "floor' OR 1=1 --"])
def test_level_features_filters_before_materializing_and_preserves_records(tmp_path, level_id):
    path = tmp_path / "floor-filter.gpkg"
    writer = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    layer = writer.CreateLayer("detail_26910", geom_type=ogr.wkbLineString)
    names = ("detail_id", "use_type", "level_id")
    for name in names:
        assert layer.CreateField(ogr.FieldDefn(name, ogr.OFTString)) == 0
    expected = []
    for index in range(15):
        matches = index in (2, 7, 12)
        other_level = level_id.swapcase() if index == 0 else level_id + "_OTHER"
        value = level_id if matches else other_level
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("detail_id", f"detail-{index}")
        feature.SetField("level_id", value)
        if index != 7:
            feature.SetField("use_type", "wall")
            feature.SetGeometry(ogr.CreateGeometryFromWkt(
                f"LINESTRING ({index}.125 1.25, {index}.875 2.625, {index}.9375 3.75)"
            ))
        assert layer.CreateFeature(feature) == 0
        if matches:
            geometry = feature.GetGeometryRef()
            expected.append({
                "detail_id": f"detail-{index}",
                "use_type": None if index == 7 else "wall",
                "level_id": level_id,
                "geometry": json.loads(geometry.ExportToJson()) if geometry else None,
            })
        feature = None
    layer = None
    writer = None
    reader = ogr.Open(str(path), 0)
    dataset = CountingDataset(reader)
    records = ArtifactRepository._level_features(dataset, "detail_26910", level_id, names)
    assert records == expected, "Every field, vertex, null geometry and original order survives"
    assert dataset.layer.visited == [row["detail_id"] for row in expected], (
        "OGR must filter the exact level before materializing Python features; "
        "unrelated floor rows were scanned"
    )
    dataset.layer.visited.clear()
    assert ArtifactRepository._level_features(dataset, "detail_26910", "absent'level", names) == []
    assert dataset.layer.visited == [], "An absent exact level must not scan unrelated rows"

@pytest.mark.parametrize("raises", [False, True])
def test_level_filter_failure_is_closed_before_iteration(raises):
    class FailedLayer:
        def SetAttributeFilter(self, expression):  # noqa: N802 - real OGR interface
            if raises:
                raise RuntimeError("Synthetic GDAL filter failure")
            return 1

        def __iter__(self):
            pytest.fail("A failed OGR filter must never fall back to an unfiltered scan")

    class FailedDataset:
        def GetLayerByName(self, name):  # noqa: N802 - real OGR interface
            return FailedLayer()

    with pytest.raises(ArtifactUnavailableError):
        ArtifactRepository._level_features(
            FailedDataset(), "detail_26910", "floor' OR 1=1 --", ("detail_id", "level_id")
        )
