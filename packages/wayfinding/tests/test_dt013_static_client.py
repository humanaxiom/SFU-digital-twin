"""RED contract tests for the DT-013 framework-free static explorer."""

import re
from html.parser import HTMLParser
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
STATIC_DIR = (
    WORKSPACE_ROOT / "packages" / "wayfinding" / "src" / "wayfinding" / "demo" / "static"
)


class _ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _read_asset(name: str) -> str:
    path = STATIC_DIR / name
    assert path.is_file(), f"DT-013 static asset is missing: {path.relative_to(WORKSPACE_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_explorer_uses_local_assets_and_semantic_controls():
    html = _read_asset("index.html")
    parser = _ContractParser()
    parser.feed(html)
    tags = parser.tags

    assert any(tag == "select" and attrs.get("id") == "facility-select" for tag, attrs in tags)
    assert any(tag == "select" and attrs.get("id") == "level-select" for tag, attrs in tags)
    assert any(tag == "svg" and attrs.get("aria-labelledby") for tag, attrs in tags)
    assert any(tag == "form" and attrs.get("id") == "assistant-form" for tag, attrs in tags)
    assert any(tag == "input" and attrs.get("maxlength") == "500" for tag, attrs in tags)
    assert any(tag == "details" for tag, _attrs in tags)
    assert any(attrs.get("aria-live") in {"polite", "assertive"} for _tag, attrs in tags)

    local_references = [
        attrs[attribute]
        for _tag, attrs in tags
        for attribute in ("src", "href")
        if attrs.get(attribute)
    ]
    assert "styles.css" in local_references
    assert "app.js" in local_references
    assert all(not re.match(r"(?:https?:)?//", reference) for reference in local_references)


def test_client_uses_safe_text_insertion_and_keyboard_room_alternative():
    javascript = _read_asset("app.js")

    assert "textContent" in javascript or "createTextNode" in javascript
    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert unsafe_api not in javascript
    assert re.search(r"createElement\([\"']button[\"']\)", javascript), (
        "The room list must provide a keyboard-operable alternative to SVG polygons"
    )
    assert "keydown" in javascript or ".focus(" in javascript
    assert "fetch(" in javascript
    assert "http://" not in javascript
    assert "https://" not in javascript


def test_floor_control_groups_real_levels_by_vertical_order():
    javascript = _read_asset("app.js")

    assert "vertical_order" in javascript
    assert 'request("/demo/v1/levels")' in javascript
    assert "levelsByOrder" in javascript


def test_landmarks_support_pointer_keyboard_and_selected_record_details():
    javascript = _read_asset("app.js")

    assert "selectLandmark" in javascript
    assert 'marker.setAttribute("role", "button")' in javascript
    assert 'marker.addEventListener("click"' in javascript
    assert 'marker.addEventListener("keydown"' in javascript


def test_client_discloses_deterministic_limits_without_route_or_ai_branding():
    html = _read_asset("index.html")
    visible_text = re.sub(r"<[^>]+>", " ", html).lower()

    assert "deterministic data assistant" in visible_text
    assert "not an llm" in visible_text
    assert "data and limitations" in visible_text
    assert "destination" in visible_text
    assert "not paths" in visible_text
    assert all(term in visible_text for term in ("door width", "path width", "slope", "surface"))
    assert not re.search(
        r"(?:route|nearest|distance|travel time)[^<]{0,30}(?:button|toggle)",
        html,
        re.I,
    )
    assert not re.search(r"\b(?:ai-powered|generative ai|chatgpt|copilot)\b", visible_text)

