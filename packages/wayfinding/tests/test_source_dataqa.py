"""Explicit read-only source QA, separate from artifact-only validation."""

from pathlib import Path

import pytest

SOURCE = Path("/data/IndoorWayfinding.gdb")


@pytest.mark.source_dataqa
def test_source_layer_counts_match_accepted_profile():
    if not SOURCE.is_dir():
        pytest.skip("Source QA requires source-etl; make dataqa-source preflights the mount")
    from osgeo import ogr

    dataset = ogr.Open(str(SOURCE), 0)
    assert dataset is not None, "Source GDB must open read-only"
    expected = {
        "Facilities_AQ_SH_ECC": 3,
        "Levels_AQ_SH_ECC": 11,
        "Units_AQ_SH_ECC": 1210,
        "Pathways_AQ_SH_ECC": 22426,
        "Transitions_AQ_SH_ECC": 63,
        "Landmarks_AQ_SH_ECC": 41,
        "Details_AQ_SH_ECC": 55593,
    }
    for name, count in expected.items():
        layer = dataset.GetLayerByName(name)
        assert layer is not None, f"Missing source layer: {name}"
        assert layer.GetFeatureCount() == count, f"Source count drift: {name}"
