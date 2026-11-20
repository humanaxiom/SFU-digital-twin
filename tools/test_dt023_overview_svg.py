#!/usr/bin/env python3
"""Focused checks for the standalone DT-023 overview SVG."""

from xml.etree import ElementTree as ET

from dt023_overview_preview import render_svg
from osgeo import ogr

NS = {"svg": "http://www.w3.org/2000/svg"}


def test_review_map_renders_four_buildings_and_keeps_interior_rings():
    polygon = ogr.CreateGeometryFromWkt(
        "POLYGON ((0 0, 0 30, 30 30, 30 0, 0 0), "
        "(10 10, 20 10, 20 20, 10 20, 10 10))"
    )
    pilot = [
        (code, name, polygon)
        for code, name in (
            ("AQ", "Academic Quadrangle"),
            ("ECC", "East Concourse Cafeteria"),
            ("SH", "Strand Hall"),
        )
    ]
    text = render_svg(pilot, polygon)
    svg = ET.fromstring(text)
    assert svg.attrib["aria-labelledby"] == "title description"
    paths = svg.findall(".//svg:path[@data-building]", NS)
    assert [path.attrib["data-building"] for path in paths] == ["AQ", "ECC", "SH", "ASB"]
    for path in paths:
        assert path.attrib["fill-rule"] == "evenodd"
        assert path.attrib["d"].count("M ") == path.attrib["d"].count("Z") == 2
    assert paths[-1].attrib["data-building-number"] == "038"
    assert "Pilot indoor data" in text
    assert "ASB footprint only" in text
