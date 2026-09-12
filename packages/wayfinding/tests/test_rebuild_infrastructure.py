"""Contracts for the isolated revised-source rebuild harness."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[3]
COMPOSE = ROOT / "infra" / "docker-compose.rebuild.yml"
MAKEFILE = ROOT / "Makefile"


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_rebuild_services_are_docker_only_and_isolated() -> None:
    compose = _compose()
    services = compose["services"]
    assert set(services) == {"artifact-build", "source-build", "source-review"}
    for service in services.values():
        assert service["network_mode"] == "none"
        assert "../build/experiments:/workspace/build/experiments:rw" in service["volumes"]
        assert "..:/workspace:ro" in service["volumes"]
        assert any(
            str(item).startswith("/workspace/data:ro,noexec,nosuid")
            for item in service["tmpfs"]
        )
        assert "pip" not in " ".join(service["command"])
    artifact = services["artifact-build"]["volumes"]
    assert not any("/source" in item or "/sources" in item or ".gdb" in item for item in artifact)


def test_rebuild_source_mounts_have_required_boundaries() -> None:
    services = _compose()["services"]
    source = services["source-build"]["volumes"]
    review = services["source-review"]["volumes"]
    assert "../data/IndoorWayfinding.gdb:/source/IndoorWayfinding.gdb:ro" in source
    assert "../data:/sources:ro" in review
    assert all(
        ":rw" not in item or "/workspace/build/experiments" in item
        for item in source + review
    )


def test_make_etl_aliases_rebuild_and_fast_list_covers_rebuild_contracts() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "etl: rebuild" in makefile
    assert "sh tools/rebuild.sh build" in makefile
    check_fast = (ROOT / "tools" / "check-fast.sh").read_text(encoding="utf-8")
    for name in (
        "test_rebuild.py",
        "test_build_semantics.py",
        "test_source_review.py",
        "test_rebuild_infrastructure.py",
    ):
        assert name in check_fast
    assert "tests/gate/test_rebuild_launcher.sh" in check_fast
