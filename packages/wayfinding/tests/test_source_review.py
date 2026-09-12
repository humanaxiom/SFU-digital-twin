"""Source comparison uses real disposable OGR datasets, never campus inputs."""

import hashlib
import json
import subprocess
import sys

import pytest
from osgeo import ogr, osr

from wayfinding.etl.source_review import hash_directory, review_sources


def make_source(path, *, revised=False, broken=False, epsg=26910):
    reference = osr.SpatialReference()
    reference.ImportFromEPSG(epsg)
    dataset = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(str(path))
    for name in (
        "Facilities",
        "Levels",
        "Units",
        "Pathways",
        "Transitions",
        "Landmarks",
        "Details",
    ):
        suffix = "_Revised" if revised and name == "Pathways" else ""
        layer = dataset.CreateLayer(
            f"{name}_AQ_SH_ECC{suffix}", reference, ogr.wkbMultiLineString25D
        )
        for field, kind in (
            ("FACILITY_ID", ogr.OFTString),
            ("LEVEL_ID", ogr.OFTString),
            ("NAME", ogr.OFTString),
            ("VERTICAL_ORDER", ogr.OFTInteger),
            ("LENGTH_3D", ogr.OFTReal),
            ("TRAVEL_DIRECTION", ogr.OFTInteger),
        ):
            layer.CreateField(ogr.FieldDefn(field, kind))
        if name == "Transitions":
            continue
        ids = ([1, 2, 4] if revised else [1, 2, 3]) if name == "Pathways" else [1]
        for fid in ids:
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetFID(fid)
            feature.SetField("FACILITY_ID", "F")
            feature.SetField("LEVEL_ID", "F_L")
            feature.SetField("NAME", "changed" if revised and fid == 2 else "original")
            feature.SetField("VERTICAL_ORDER", 0)
            feature.SetField("LENGTH_3D", 1.0)
            feature.SetField("TRAVEL_DIRECTION", 1)
            geometry = "LINESTRING Z (500000 5450000 0, 500001 5450000 0)"
            if broken and name == "Pathways" and fid == 4:
                feature.SetFieldNull("FACILITY_ID")
                feature.SetFieldNull("LEVEL_ID")
                geometry = (
                    "MULTILINESTRING Z ((500000 5450000 0, 500001 5450000 0),"
                    " (500003 5450000 0, 500004 5450000 0))"
                )
            feature.SetGeometry(ogr.CreateGeometryFromWkt(geometry))
            assert layer.CreateFeature(feature) == 0
    dataset = None


@pytest.fixture
def sources(tmp_path):
    legacy, revised, supplemental = [
        tmp_path / name for name in ("old.gdb", "new.gdb", "extra.gdb")
    ]
    make_source(legacy)
    make_source(revised, revised=True, broken=True)
    dataset = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(str(supplemental))
    layer = dataset.CreateLayer("Attachment", geom_type=ogr.wkbNone)
    layer.CreateField(ogr.FieldDefn("PRIVATE_VALUE", ogr.OFTString))
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetField("PRIVATE_VALUE", "DO NOT DISCLOSE")
    layer.CreateFeature(feature)
    dataset = None
    return legacy, revised, supplemental


def test_comparison_and_diagnostics_are_deterministic(sources):
    report = review_sources(*sources)
    assert report == review_sources(*sources)
    pathways = report["layers"]["Pathways"]
    assert pathways["counts"] == {
        "legacy": 3,
        "revised": 3,
        "added": 1,
        "removed": 1,
        "changed": 1,
        "unchanged": 1,
    }
    assert pathways["source_layers"]["revised"] == "Pathways_AQ_SH_ECC_Revised"
    assert pathways["changes"]["added"][0]["fid"] == 4
    assert len(report["layers"]) == 7
    problem = next(item for item in report["diagnostics"] if item["fid"] == 4)
    assert problem["snapshot"] == "revised"
    assert {"missing_facility_id", "missing_level_id", "discontinuous_multipart"} <= set(
        problem["reasons"]
    )
    assert len(problem["fingerprint"]) == 64
    assert report["build_readiness"]["revised"]["status"] == "blocked"
    assert "DO NOT DISCLOSE" not in json.dumps(report)


def test_directory_hash_contract_and_rejections(tmp_path):
    directory = tmp_path / "source"
    directory.mkdir()
    with pytest.raises(ValueError, match="empty"):
        hash_directory(directory)
    (directory / "z").write_bytes(b"z")
    (directory / "a").write_bytes(b"a")
    expected = hashlib.sha256(
        b"".join(
            name.encode() + b"\0" + hashlib.sha256(name.encode()).hexdigest().encode() + b"\n"
            for name in ("a", "z")
        )
    ).hexdigest()
    assert hash_directory(directory) == {"sha256": expected, "files": 2, "bytes": 2}
    (directory / "link").symlink_to(directory / "a")
    with pytest.raises(ValueError, match="symlink"):
        hash_directory(directory)
    with pytest.raises(FileNotFoundError):
        hash_directory(tmp_path / "missing")


def test_cli_refuses_existing_output_and_sources(sources, tmp_path):
    command = [sys.executable, "-m", "wayfinding.etl.source_review"]
    for flag, source in zip(("--legacy", "--revised", "--supplemental"), sources, strict=True):
        command.extend((flag, str(source)))
    output = tmp_path / "report.json"
    result = subprocess.run([*command, "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original = output.read_bytes()
    result = subprocess.run([*command, "--output", str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert output.read_bytes() == original
    forbidden = sources[0] / "report.json"
    assert (
        subprocess.run([*command, "--output", str(forbidden)], capture_output=True).returncode != 0
    )
    assert not forbidden.exists()
    linked = tmp_path / "linked.json"
    linked.symlink_to(output)
    assert subprocess.run([*command, "--output", str(linked)], capture_output=True).returncode != 0
    assert output.read_bytes() == original
    parent_link = tmp_path / "source_alias"
    parent_link.symlink_to(sources[0], target_is_directory=True)
    alias_output = parent_link / "new.json"
    assert (
        subprocess.run([*command, "--output", str(alias_output)], capture_output=True).returncode
        != 0
    )
    assert not alias_output.exists()


def test_relationship_weight_and_direction_errors(sources):
    dataset = ogr.Open(str(sources[1]), 1)
    layer = dataset.GetLayerByName("Pathways_AQ_SH_ECC_Revised")
    feature = layer.GetFeature(1)
    feature.SetField("FACILITY_ID", "UNKNOWN")
    feature.SetField("LENGTH_3D", 0)
    feature.SetField("TRAVEL_DIRECTION", 2)
    layer.SetFeature(feature)
    feature = layer.GetFeature(2)
    feature.SetField("LEVEL_ID", "UNKNOWN")
    layer.SetFeature(feature)
    dataset = None
    report = review_sources(*sources)
    problem = next(
        item for item in report["diagnostics"] if item["snapshot"] == "revised" and item["fid"] == 1
    )
    assert {
        "orphan_facility_id",
        "facility_level_mismatch",
        "invalid_length_3d",
        "unsupported_travel_direction",
    } <= set(problem["reasons"])
    assert any("orphan_level_id" in item["reasons"] for item in report["diagnostics"])


def test_duplicate_level_identity_blocks_review(sources):
    dataset = ogr.Open(str(sources[0]), 1)
    layer = dataset.GetLayerByName("Levels_AQ_SH_ECC")
    feature = layer.GetFeature(1)
    feature.SetFID(2)
    layer.CreateFeature(feature)
    dataset = None
    report = review_sources(*sources)
    assert any("duplicate_level_id" in item["reasons"] for item in report["diagnostics"])


def test_missing_layer_and_schema_difference(sources):
    dataset = ogr.Open(str(sources[1]), 1)
    layer = dataset.GetLayerByName("Units_AQ_SH_ECC")
    layer.CreateField(ogr.FieldDefn("NEW_FIELD", ogr.OFTString))
    index = next(
        i
        for i in range(dataset.GetLayerCount())
        if dataset.GetLayer(i).GetName() == "Details_AQ_SH_ECC"
    )
    dataset.DeleteLayer(index)
    dataset = None
    report = review_sources(*sources)
    assert report["layers"]["Units"]["schema_changed"]
    assert report["layers"]["Details"]["counts"]["removed"] == 1
    assert (
        "missing_layer:Details_AQ_SH_ECC"
        in report["build_readiness"]["revised"]["structural_issues"]
    )


def test_geometry_fingerprint_changes_independently_of_attributes(sources):
    dataset = ogr.Open(str(sources[1]), 1)
    layer = dataset.GetLayerByName("Pathways_AQ_SH_ECC_Revised")
    feature = layer.GetFeature(1)
    feature.SetGeometry(
        ogr.CreateGeometryFromWkt("LINESTRING Z (500000 5450000 0, 500000 5450001 0)")
    )
    layer.SetFeature(feature)
    dataset = None
    report = review_sources(*sources)
    changed = report["layers"]["Pathways"]["changes"]["changed"][0]
    assert changed["fid"] == 1
    assert changed["legacy"]["attribute_sha256"] == changed["revised"]["attribute_sha256"]
    assert changed["legacy"]["geometry_sha256"] != changed["revised"]["geometry_sha256"]


def test_crs_change_blocks_snapshot(sources, tmp_path):
    alternate = tmp_path / "alternate.gdb"
    make_source(alternate, revised=True, epsg=26911)
    report = review_sources(sources[0], alternate, sources[2])
    assert report["layers"]["Pathways"]["crs_changed"]
    assert report["build_readiness"]["revised"]["status"] == "blocked"
    assert (
        "unsupported_crs:Pathways_AQ_SH_ECC_Revised"
        in report["build_readiness"]["revised"]["structural_issues"]
    )


def test_transition_semantics_and_endpoint_relationships(sources):
    dataset = ogr.Open(str(sources[0]), 1)
    layer = dataset.GetLayerByName("Transitions_AQ_SH_ECC")
    for field, kind in (
        ("LEVEL_NAME_FROM", ogr.OFTString),
        ("LEVEL_NAME_TO", ogr.OFTString),
        ("TRANSITION_TYPE", ogr.OFTInteger),
    ):
        layer.CreateField(ogr.FieldDefn(field, kind))
    feature = ogr.Feature(layer.GetLayerDefn())
    for field, value in {
        "FACILITY_ID": "F",
        "LEVEL_NAME_FROM": "L",
        "LEVEL_NAME_TO": "L",
        "TRANSITION_TYPE": 2,
        "TRAVEL_DIRECTION": 1,
        "LENGTH_3D": 1,
    }.items():
        feature.SetField(field, value)
    feature.SetGeometry(
        ogr.CreateGeometryFromWkt("LINESTRING Z (500000 5450000 0, 500000 5450000 3)")
    )
    layer.CreateFeature(feature)
    dataset = None
    report = review_sources(*sources)
    assert not any(
        item["snapshot"] == "legacy" and "Transitions" in item["layer"]
        for item in report["diagnostics"]
    )
    dataset = ogr.Open(str(sources[0]), 1)
    layer = dataset.GetLayerByName("Transitions_AQ_SH_ECC")
    feature = layer.GetFeature(1)
    feature.SetField("LEVEL_NAME_TO", "unknown")
    feature.SetField("TRANSITION_TYPE", 99)
    layer.SetFeature(feature)
    dataset = None
    report = review_sources(*sources)
    problem = next(item for item in report["diagnostics"] if "Transitions" in item["layer"])
    assert {"orphan_level_to", "unsupported_transition_type"} <= set(problem["reasons"])


def test_child_layers_use_declared_level_relationship_without_facility_field(sources):
    """Real Units/Details/Landmarks schemas carry LEVEL_ID, not FACILITY_ID."""
    dataset = ogr.Open(str(sources[0]), 1)
    for name in ("Units", "Details", "Landmarks"):
        layer = dataset.GetLayerByName(f"{name}_AQ_SH_ECC")
        assert layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("FACILITY_ID")) == 0
    dataset = None
    report = review_sources(*sources)
    assert not [item for item in report["diagnostics"] if item["snapshot"] == "legacy"]
    dataset = ogr.Open(str(sources[0]), 1)
    layer = dataset.GetLayerByName("Units_AQ_SH_ECC")
    feature = layer.GetFeature(1)
    feature.SetField("LEVEL_ID", "UNKNOWN")
    layer.SetFeature(feature)
    dataset = None
    report = review_sources(*sources)
    problem = next(item for item in report["diagnostics"] if item["snapshot"] == "legacy")
    assert problem["reasons"] == ["orphan_level_id"]
