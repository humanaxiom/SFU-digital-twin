"""Static route controls and authored geometry contracts."""

import re
from html.parser import HTMLParser
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
STATIC_DIR = WORKSPACE_ROOT / "packages/wayfinding/src/wayfinding/demo/static"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.controls: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.controls[element_id] = attributes


def _asset(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def test_preview_is_the_route_form_submit_and_other_actions_are_explicit():
    html = _asset("index.html")
    parser = _Parser()
    parser.feed(html)
    controls = parser.controls

    assert re.search(r'<button id="route-submit" type="submit">Preview route</button>', html)
    for element_id in ("route-swap", "route-clear", "room-start-here", "room-directions-here"):
        assert controls[element_id]["type"] == "button"
    for element_id in ("room-start-here", "room-directions-here"):
        assert "disabled" in controls[element_id]


def test_draft_and_committed_route_identity_have_distinct_announcements():
    parser = _Parser()
    parser.feed(_asset("index.html"))
    controls = parser.controls

    for element_id in ("route-draft-status", "route-request-status", "room-route-status"):
        assert controls[element_id]["role"] == "status"
    for element_id in ("route-committed-identity", "map-route-identity"):
        assert controls[element_id]["aria-live"] == "polite"
    assert "map-route-identity" in (controls["floor-map"]["aria-describedby"] or "").split()


def test_draft_and_committed_accessibility_disclosures_have_distinct_controls():
    html = _asset("index.html")
    parser = _Parser()
    parser.feed(html)

    assert "hidden" in parser.controls["route-profile-help"]
    assert "hidden" in parser.controls["route-accessibility"]
    assert all(
        term in html.lower()
        for term in (
            "elevators only; stairs excluded",
            "accessibility is not verified",
            "door width",
            "path width",
            "slope",
            "powered doors",
            "surface",
        )
    )


def test_client_renders_service_geometry_only_without_synthetic_connectors():
    javascript = _asset("app.js")

    # Guidance geometries and their explicit step references are the only
    # route spans the client should draw.
    assert "activeRoute?.guidance" in javascript or "activeRoute.guidance" in javascript
    assert "guidance.geometries" in javascript
    assert "step.geometry_ids" in javascript
    assert "item.geometry_id" in javascript
    assert "svgPath(item" in javascript
    assert "pathData(geometry)" in javascript

    # Room anchors, graph node IDs, and transitions are not path inputs.
    assert not re.search(r"(?:centroid|anchor|node_id|edge_ids).*pathData", javascript, re.I)
    assert not re.search(r"(?:centroid|anchor|node_id|edge_ids).*svgPath", javascript, re.I)


def test_mobile_route_controls_allow_panels_to_shrink_without_overflow():
    stylesheet = _asset("styles.css")

    assert re.search(r"\.map-panel,\s*\.side-panel\s*\{[^}]*min-width:\s*0", stylesheet)
    assert re.search(r"select,\s*input\s*\{[^}]*max-width:\s*100%", stylesheet)
