"""Exercise real GDAL extraction without private campus source data."""

import pytest
from osgeo import ogr, osr

from wayfinding.etl.extract import extract_to_gpkg


def test_small_filegdb_roundtrip_preserves_attributes_and_dual_crs(tmp_path):
    source = tmp_path / "source.gdb"
    output = tmp_path / "output.gpkg"
    reference = osr.SpatialReference()
    reference.ImportFromEPSG(26910)
    dataset = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(str(source))
    assert dataset is not None
    names = ("Facilities", "Levels", "Units", "Pathways", "Transitions", "Landmarks", "Details")
    for name in names:
        layer = dataset.CreateLayer(f"{name}_AQ_SH_ECC", reference, ogr.wkbPoint25D)
        layer.CreateField(ogr.FieldDefn("NAME", ogr.OFTString))
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("NAME", f"fixture {name}")
        feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT Z (500000 5450000 12)"))
        assert layer.CreateFeature(feature) == 0
        feature = None
        layer = None
    dataset = None

    counts = extract_to_gpkg(source, output)
    assert counts == {f"{name}_{suffix}": 1 for name in names for suffix in ("26910", "wgs84")}
    result = ogr.Open(str(output), 0)
    assert result.GetLayerCount() == 14
    for name in names:
        for suffix, epsg, dimensions in (("26910", "26910", 3), ("wgs84", "4326", 2)):
            layer = result.GetLayerByName(f"{name}_{suffix}")
            assert layer.GetSpatialRef().GetAuthorityCode(None) == epsg
            feature = layer.GetNextFeature()
            assert feature.GetField("NAME") == f"fixture {name}"
            geometry = feature.GetGeometryRef()
            assert geometry.GetCoordinateDimension() == dimensions
            if suffix == "26910":
                assert geometry.GetPoint() == pytest.approx((500000, 5450000, 12))
            else:
                assert geometry.GetX() == pytest.approx(-123, abs=0.001)
                assert 49 < geometry.GetY() < 50
            feature = None
            layer = None
    result = None
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        extract_to_gpkg(source, output, overwrite=False)
    assert output.read_bytes() == before
    assert extract_to_gpkg(source, output, overwrite=True) == counts
