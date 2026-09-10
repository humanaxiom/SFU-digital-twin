"""RED static-client contracts for the bounded indoor route workflow."""

import re
from html.parser import HTMLParser
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
STATIC_DIR = WORKSPACE_ROOT / "packages/wayfinding/src/wayfinding/demo/static"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _asset(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def test_route_controls_are_exact_semantic_and_keyboard_operable():
    parser = _Parser()
    parser.feed(_asset("index.html"))
    tags = parser.tags

    for control_id in ("route-origin", "route-destination", "route-profile"):
        assert any(tag == "select" and attrs.get("id") == control_id for tag, attrs in tags)
    assert any(tag == "form" and attrs.get("id") == "route-form" for tag, attrs in tags)
    assert any(
        tag == "button" and attrs.get("type") == "submit" and attrs.get("id") == "route-submit"
        for tag, attrs in tags
    )
    assert any(attrs.get("aria-live") == "assertive" for _tag, attrs in tags)


def test_profile_control_offers_only_default_and_elevator_only():
    html = _asset("index.html")
    profile = re.search(r'<select[^>]+id="route-profile"[^>]*>(.*?)</select>', html, re.S)

    assert profile
    options = re.findall(r'<option[^>]+value="([^"]+)"', profile.group(1))
    assert options == ["default", "elevator_only"]
    assert re.search(r'<option[^>]+value="default"[^>]*selected', profile.group(1))


def test_client_posts_exact_route_contract_and_renders_graph_geometry_only():
    javascript = _asset("app.js")

    assert 'request("/demo/v1/route"' in javascript
    assert all(term in javascript for term in ("origin", "destination", "unit_id", "profile"))
    assert all(term in javascript for term in ("geometries", "edge_ids", "network_distance_m"))
    assert "attachment_distance_m" in javascript
    assert "connector" not in javascript.lower() or "connector geometry" not in javascript.lower()
    assert "http://" not in javascript and "https://" not in javascript


def test_route_overlay_and_steps_follow_the_active_level_without_layout_shift():
    html = _asset("index.html")
    javascript = _asset("app.js")
    css = _asset("styles.css")

    assert 'id="route-overlay"' in html
    assert 'id="route-steps"' in html
    assert "activeStep" in javascript
    assert "level_id" in javascript
    assert "selectLevel" in javascript or "loadLevel" in javascript
    assert re.search(r"#route-overlay|\.route-segment", css)
    assert re.search(r"min-height|max-height|block-size", css)


def test_success_failure_and_approximate_anchor_disclosures_are_visible():
    html = _asset("index.html")
    text = re.sub(r"<[^>]+>", " ", html).lower()

    assert "indoor pathway route between approximate room anchors" in text
    assert "room-to-anchor" in text
    assert "not represented or verified" in text
    assert "disconnected" in text
    assert all(term in text for term in ("closures", "opening hours", "door access"))
    assert "elevator status" in text


def test_elevator_only_disclosure_is_complete_and_never_overclaims():
    text = re.sub(r"<[^>]+>", " ", _asset("index.html")).lower()

    assert "elevators only; stairs excluded" in text
    assert all(
        term in text
        for term in ("door width", "path width", "slope", "powered doors", "surface")
    )
    assert "wheelchair-certified" not in text
    assert "guaranteed step-free" not in text


def test_route_ui_keeps_legacy_provenance_and_has_no_external_or_deferred_capabilities():
    combined = "\n".join(_asset(name) for name in ("index.html", "styles.css", "app.js"))
    lowered = combined.lower()

    assert "legacy" in lowered
    assert "sha-256" in lowered or "sha256" in lowered
    assert not re.search(r"(?:https?:)?//", combined)
    for forbidden in (
        "maplibregl",
        "new maplibre",
        "pmtiles://",
        "navigator.geolocation",
        'request("/v1/route"',
    ):
        assert forbidden not in lowered


def test_route_layout_has_explicit_mobile_behavior_and_no_horizontal_overflow():
    css = _asset("styles.css")

    assert re.search(r"@media\s*\([^)]*max-width", css)
    assert "overflow-x" in css
    assert re.search(r"route[^}]*grid-template|grid-template[^}]*route", css, re.S | re.I)
