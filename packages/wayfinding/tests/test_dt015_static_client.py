"""RED client state-machine and route-entry parity contracts for DT-015."""

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


def _function_body(javascript: str, name: str) -> str:
    match = re.search(
        rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{(?P<body>[\s\S]*?)\n\}}",
        javascript,
    )
    assert match, f"app.js must define the shared {name} function"
    return match.group("body")


def test_first_room_activation_sets_origin_without_request():
    javascript = _asset("app.js")
    activation = _function_body(javascript, "activateRouteEndpoint")

    assert re.search(r"(?:empty|origin_selected|routeSelection)", javascript)
    assert "routeOrigin.value" in activation
    assert re.search(r"routeDestination\.value\s*=\s*[\"'][\"']", activation)
    first_selection = re.search(
        r"if\s*\([^)]*(?:empty|!\s*routeOrigin\.value)[^)]*\)\s*\{(?P<body>[\s\S]*?)\n\s*\}",
        activation,
    )
    assert first_selection, "first activation must have an explicit origin-only transition"
    assert "requestRoute(" not in first_selection.group("body")


def test_second_distinct_room_activation_sets_destination_and_routes():
    javascript = _asset("app.js")
    activation = _function_body(javascript, "activateRouteEndpoint")
    request_route = _function_body(javascript, "requestRoute")

    assert re.search(
        r"unitId\s*!==\s*routeOrigin\.value|routeOrigin\.value\s*!==\s*unitId",
        activation,
    )
    assert "routeDestination.value" in activation
    assert activation.count("requestRoute(") == 1
    assert 'request("/demo/v1/route"' in request_route
    assert all(
        contract in request_route
        for contract in (
            "origin: { unit_id:",
            "destination: { unit_id:",
            "profile:",
            "renderRoute(",
        )
    )


def test_keyboard_room_activation_matches_pointer_state_machine():
    javascript = _asset("app.js")

    assert javascript.count("activateRouteEndpoint(item.unit_id") >= 3, (
        "map clicks, Enter/Space, and room-list buttons must share endpoint activation"
    )
    assert re.search(r'event\.key\s*===\s*["\']Enter["\']', javascript)
    assert re.search(r'event\.key\s*===\s*["\'] ["\']', javascript)
    assert re.search(r"aria-live", _asset("index.html"), re.I)
    assert re.search(
        r"(?:origin|destination).*(?:selected|set)|(?:selected|set).*(?:origin|destination)",
        javascript,
        re.I,
    )


def test_endpoint_clear_swap_reselect_and_manual_select_fallback():
    parser = _Parser()
    parser.feed(_asset("index.html"))
    ids = {attrs.get("id") for _tag, attrs in parser.tags}
    javascript = _asset("app.js")

    assert {"route-clear", "route-swap"} <= ids
    assert re.search(r"routeClear\.addEventListener|querySelector\([\"']#route-clear", javascript)
    assert re.search(r"routeSwap\.addEventListener|querySelector\([\"']#route-swap", javascript)
    assert re.search(r"routeOrigin\.addEventListener\([\"']change", javascript)
    assert re.search(r"routeDestination\.addEventListener\([\"']change", javascript)
    assert re.search(
        r"origin[^\n]*!==[^\n]*destination|destination[^\n]*!==[^\n]*origin",
        javascript,
    )
    assert re.search(r"(?:generation|requestGeneration)", javascript)
    assert re.search(r"classList\.(?:toggle|add)\([^\n]*(?:origin|destination)", javascript)


def test_route_failure_clears_stale_overlay_and_keeps_disclosures():
    javascript = _asset("app.js")
    renderer = _function_body(javascript, "renderRoute")

    assert re.search(r"body\.status\s*!==\s*200", renderer)
    assert re.search(r"activeRoute\s*=\s*null|replaceChildren\(\)", renderer)
    assert "renderRouteOverlay(" in renderer
    assert "routeAccessibility.hidden = body.profile !== \"elevator_only\"" in renderer
    assert all(
        term in _asset("index.html").lower()
        for term in (
            "elevators only; stairs excluded",
            "door width",
            "path width",
            "slope",
            "powered doors",
            "surface",
        )
    )


def test_assistant_success_renders_same_route_as_direct_request():
    javascript = _asset("app.js")
    assistant_submit = re.search(
        r"assistantForm\.addEventListener\([\"']submit[\"'][\s\S]*?\n\}\);",
        javascript,
    )

    assert assistant_submit
    body = assistant_submit.group(0)
    assert re.search(r"parseExactDirections|parseDirectionRequest", body)
    assert "requestRoute(" in body
    assert 'request("/demo/v1/assistant"' in body
    assert re.search(r"if\s*\([^)]*(?:direction|routeRequest)", body)
    assert re.search(r"(?:else|return)[\s\S]*request\([\"']/demo/v1/assistant", body)
    assert _function_body(javascript, "requestRoute").count('request("/demo/v1/route"') == 1


def test_assistant_failure_and_mobility_disclosure_match_route_service():
    javascript = _asset("app.js")
    parser_name = (
        "parseExactDirections"
        if "function parseExactDirections" in javascript
        else "parseDirectionRequest"
    )
    parser = _function_body(javascript, parser_name)
    request_route = _function_body(javascript, "requestRoute")

    assert "elevator_only" in parser
    assert "default" in parser
    assert re.search(r"(?:mobility|elevator|accessible)", parser, re.I)
    assert "renderRoute(" in request_route
    assert re.search(r"catch[\s\S]*renderRoute\(", request_route)
    assert 'request("/demo/v1/assistant"' not in request_route
    assert "stairs" not in parser.lower() or "elevator_only" in parser


def test_third_and_same_room_activations_are_deterministic_and_synchronized():
    javascript = _asset("app.js")
    activation = _function_body(javascript, "activateRouteEndpoint")

    assert re.search(r"(?:complete|failed)", activation)
    assert re.search(
        r"unitId\s*===\s*routeOrigin\.value|routeOrigin\.value\s*===\s*unitId",
        activation,
    )
    assert re.search(r"(?:return|no request)", activation, re.I)
    assert all(control in activation for control in ("routeOrigin.value", "routeDestination.value"))
    assert re.search(r"(?:activeRoute\s*=\s*null|clearRoute)", activation)


def test_client_renders_service_geometry_only_without_synthetic_connectors():
    javascript = _asset("app.js")
    overlay = _function_body(javascript, "renderRouteOverlay")
    request_route = _function_body(javascript, "requestRoute")

    assert "activeRoute.geometries" in overlay
    assert re.search(r"\.filter\(\([^)]*\)\s*=>\s*[^\n]*level_id\s*===\s*levelId", overlay)
    assert "svgPath(item" in overlay
    assert not re.search(
        r"(?:centroid|anchor|connector|node_id|edge_ids).*pathData",
        javascript,
        re.I,
    )
    assert not re.search(r"(?:geometry|distance|reachability)\s*=", request_route, re.I)
