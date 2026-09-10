"""Closed, deterministic query handling for the artifact demonstration."""

from __future__ import annotations

from typing import Any

from .artifact import ArtifactRepository

LIMITATIONS_ID = "phase1-artifact-only"
NOT_VERIFIED = ["door_width", "path_width", "slope", "powered_doors", "surface"]
ROUTING_REFUSAL = (
    "Routing is not available in this demo because no routing service or unit connectors "
    "have been implemented."
)


def _evidence(
    repository: ArtifactRepository,
    layer: str,
    feature_id: str,
    fields: list[str],
) -> dict[str, Any]:
    return {
        "artifact_sha256": repository.artifact_sha256,
        "layer": layer,
        "feature_id": feature_id,
        "fields": fields,
    }


def _response(kind: str, text: str, **values: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text,
        "limitations_id": LIMITATIONS_ID,
        "generated_by": "deterministic_rules",
        **values,
    }


def respond(
    repository: ArtifactRepository,
    message: str,
    facility_id: str | None = None,
    level_id: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic response derived only from the artifact and map context."""
    normalized = " ".join(message.split()).casefold()
    mobility = any(
        term in normalized
        for term in ("accessible", "accessibility", "wheelchair", "mobility", "step-free")
    )
    routing = any(term in normalized for term in ("route", "directions", "path", "get me to"))
    nearest = any(term in normalized for term in ("nearest", "closest"))
    travel = any(term in normalized for term in ("distance", "travel time", "how far", "how long"))

    if routing or travel or mobility:
        text = ROUTING_REFUSAL
        values: dict[str, Any] = {}
        if mobility:
            text += (
                " Elevator-only routing is not implemented, and no path can be certified from "
                "this demo. Door width, path width, slope, powered doors, and surface are not "
                "verified."
            )
            values["not_verified"] = NOT_VERIFIED
        return _response("refusal", text, **values)
    if nearest:
        return _response(
            "refusal",
            "Nearest-place search is not available because this demo computes no proximity "
            "or distance.",
        )
    if any(term in normalized for term in ("occupancy", "open now", "opening", "elevator status")):
        return _response(
            "refusal",
            "Live occupancy, opening, and elevator status are not available.",
        )

    units = repository.units()
    exact = [
        item
        for item in units
        if " ".join((item["room_id"] or "").split()).casefold() == normalized
    ]
    if len(exact) == 1:
        item = exact[0]
        return _response(
            "room_match",
            f"Room {item['room_id']} is on level {item['level_id']}.",
            entities=[
                {
                    "type": "unit",
                    "unit_id": item["unit_id"],
                    "room_id": item["room_id"],
                    "level_id": item["level_id"],
                }
            ],
            evidence=[
                _evidence(repository, "unit_26910", item["unit_id"], ["room_id", "level_id"])
            ],
        )

    if "facilit" in normalized or "building" in normalized:
        facilities = repository.facilities()
        return _response(
            "facility_list",
            "Facilities: " + ", ".join(item["name"] for item in facilities),
            entities=[{"type": "facility", **item} for item in facilities],
            evidence=[
                _evidence(repository, "facility_26910", item["facility_id"], ["code", "name"])
                for item in facilities
            ],
        )
    if "level" in normalized or "floor" in normalized:
        levels = repository.levels(facility_id)
        return _response(
            "level_list",
            "Levels: " + ", ".join(item["short_name"] for item in levels),
            entities=[{"type": "level", **item} for item in levels],
            evidence=[
                _evidence(
                    repository,
                    "level_26910",
                    item["level_id"],
                    ["short_name", "vertical_order"],
                )
                for item in levels
            ],
        )
    if "landmark" in normalized or "amenit" in normalized:
        landmarks = repository.landmarks(level_id)
        return _response(
            "landmark_list",
            "Landmarks: " + ", ".join(item["category"] or "Uncategorized" for item in landmarks),
            entities=[{"type": "landmark", **item} for item in landmarks],
            evidence=[
                _evidence(
                    repository,
                    "landmark_26910",
                    item["landmark_id"],
                    ["category", "level_id"],
                )
                for item in landmarks
            ],
        )
    if "artifact" in normalized or "provenance" in normalized or "limitation" in normalized:
        return _response(
            "provenance",
            "This response uses normalized Phase 1 artifact records. The demo has no routing, "
            "nearest-place, live-status, search-index, or LLM capability.",
            evidence=[],
        )

    matches = [
        item
        for item in units
        if normalized
        and any(
            normalized in str(item[field] or "").casefold()
            for field in ("room_id", "use_type", "category")
        )
    ][:10]
    if matches:
        return _response(
            "choices" if len(matches) > 1 else "room_match",
            f"Found {len(matches)} literal artifact match{'es' if len(matches) != 1 else ''}.",
            entities=[
                {
                    "type": "unit",
                    "unit_id": item["unit_id"],
                    "room_id": item["room_id"],
                    "level_id": item["level_id"],
                }
                for item in matches
            ],
            evidence=[
                _evidence(
                    repository,
                    "unit_26910",
                    item["unit_id"],
                    ["room_id", "use_type", "category"],
                )
                for item in matches
            ],
        )
    return _response(
        "unknown",
        "No bounded literal match was found in the public artifact records. Try an exact room ID, "
        "or ask to list facilities, levels, or landmarks.",
        entities=[],
        evidence=[],
    )
