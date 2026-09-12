"""Structural tests for ADR-0006's hermetic build infrastructure."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
DOCKERFILE_PATH = WORKSPACE_ROOT / "infra" / "Dockerfile.build"
COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
MAKEFILE_PATH = WORKSPACE_ROOT / "Makefile"
WORKFLOW_PATH = WORKSPACE_ROOT / ".github" / "workflows" / "publish-build-image.yml"
BUILD_IMAGE = "ghcr.io/humanaxiom/sfu-digital-twin/wayfinding-build"
LOCK_CANDIDATES = (
    WORKSPACE_ROOT / "requirements.lock",
    WORKSPACE_ROOT / "requirements.txt",
    WORKSPACE_ROOT / "uv.lock",
    WORKSPACE_ROOT / "poetry.lock",
    WORKSPACE_ROOT / "Pipfile.lock",
    WORKSPACE_ROOT / "pdm.lock",
    WORKSPACE_ROOT / "infra" / "requirements.lock",
    WORKSPACE_ROOT / "infra" / "requirements.txt",
)
REQUIRED_LOCKED_PACKAGES = {
    "coverage",
    "networkx",
    "pydantic",
    "pyright",
    "pytest",
    "pytest-cov",
    "pyyaml",
    "ruff",
    "shapely",
}


def _read_required(path: Path, description: str) -> str:
    assert path.is_file(), f"Missing {description}: {path.relative_to(WORKSPACE_ROOT)}"
    return path.read_text(encoding="utf-8")


def _lock_file() -> Path:
    matches = [path for path in LOCK_CANDIDATES if path.is_file()]
    assert matches, (
        "ADR-0006 requires a checked-in dependency lock with exact versions and hashes"
    )
    assert len(matches) == 1, f"Expected one authoritative dependency lock, found: {matches}"
    return matches[0]


def _compose_services() -> dict[str, Any]:
    content = _read_required(COMPOSE_PATH, "normal Compose configuration")
    compose = yaml.safe_load(content)
    assert isinstance(compose, dict), (
        "infra/docker-compose.yml must define a services mapping"
    )
    assert isinstance(compose.get("services"), dict), (
        "infra/docker-compose.yml must define a services mapping"
    )
    services = compose["services"]
    assert {"artifact", "source-etl"}.issubset(services), (
        "Compose must define artifact and source-etl capability services"
    )
    return services


def _assert_reproducible_lock(lock_path: Path, content: str) -> None:
    """Accept hash-locked requirements or established frozen lock formats."""
    if lock_path.name.startswith("requirements"):
        blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+(?:\[[^]]+\])?==)", content)
        requirements = [block for block in blocks if re.match(r"[A-Za-z0-9_.-]+", block)]
        assert requirements, "Requirements lock must contain pinned distributions"
        for requirement in requirements:
            first_line = requirement.splitlines()[0]
            assert re.match(r"[A-Za-z0-9_.-]+(?:\[[^]]+\])?==[^\s\\]+", first_line), (
                f"Requirement is not exactly pinned: {first_line}"
            )
            assert re.search(r"--hash=sha256:[0-9a-f]{64}", requirement), (
                f"Pinned requirement has no SHA-256 hash: {first_line}"
            )
        return

    lock_signatures = {
        "uv.lock": ("[[package]]", 'hash = "sha256:'),
        "poetry.lock": ("[[package]]", "content-hash", 'hash = "sha256:'),
        "Pipfile.lock": ('"_meta"', '"hashes"', '"sha256:'),
        "pdm.lock": ("[[package]]", "content_hash", 'hash = "sha256:'),
    }
    signatures = lock_signatures.get(lock_path.name)
    assert signatures is not None, f"Unsupported dependency lock format: {lock_path.name}"
    assert all(signature in content for signature in signatures), (
        f"{lock_path.name} lacks version-integrity metadata required for frozen installs"
    )


def _volume_entries(service: dict[str, Any]) -> list[Any]:
    volumes = service.get("volumes", [])
    if isinstance(volumes, dict):
        return [{"source": source, **(value if isinstance(value, dict) else {})}
                for source, value in volumes.items()]
    return volumes


def _mount_targets(service: dict[str, Any], target: str) -> list[Any]:
    target = target.replace("\\", "/")
    matches = []
    for entry in _volume_entries(service):
        if isinstance(entry, str):
            normalized = entry.replace("\\", "/")
            if re.search(rf":{re.escape(target)}(?::(?:ro|rw))?$", normalized):
                matches.append(entry)
        elif str(entry.get("target", entry.get("destination", ""))).replace("\\", "/") == target:
            matches.append(entry)
    return matches


def _mount_is_read_only(entry: Any) -> bool:
    if isinstance(entry, str):
        return entry.replace("\\", "/").endswith(":ro")
    return entry.get("read_only") is True or entry.get("mode") == "ro"


def _tmpfs_entries(service: dict[str, Any]) -> list[Any]:
    entries = service.get("tmpfs", [])
    if isinstance(entries, dict):
        return [{"target": target, **(value if isinstance(value, dict) else {})}
                for target, value in entries.items()]
    if isinstance(entries, list):
        return entries
    return [entries]


def _tmpfs_target_and_options(entry: Any) -> tuple[str, str]:
    if isinstance(entry, str):
        target, _, options = entry.partition(":")
        return target.replace("\\", "/"), options
    target = str(entry.get("target", entry.get("destination", "")))
    options = entry.get("options", entry.get("mode", ""))
    if isinstance(options, list):
        options = ",".join(str(option) for option in options)
    return target.replace("\\", "/"), str(options)


def _make_recipes() -> dict[str, str]:
    content = _read_required(MAKEFILE_PATH, "normal target Makefile")
    return {
        match.group("target"): match.group("recipe")
        for match in re.finditer(
            r"(?m)^(?P<target>[A-Za-z0-9_.-]+):[^\n]*\n"
            r"(?P<recipe>(?:\t[^\n]*(?:\n|$))+)",
            content,
        )
    }


def test_build_dockerfile_and_dependency_lock_exist():
    assert DOCKERFILE_PATH.is_file(), "Missing infra/Dockerfile.build"
    _lock_file()


def test_dependency_lock_is_exact_hashed_and_complete():
    lock_path = _lock_file()
    content = _read_required(lock_path, "dependency lock")
    _assert_reproducible_lock(lock_path, content)
    normalized = re.sub(r"[-_.]+", "-", content.lower())
    missing = sorted(package for package in REQUIRED_LOCKED_PACKAGES if package not in normalized)
    assert not missing, f"Dependency lock is missing build-image packages: {missing}"


def test_build_dockerfile_installs_frozen_lock_at_image_build_time():
    lock_path = _lock_file()
    dockerfile = _read_required(DOCKERFILE_PATH, "build Dockerfile").lower()
    assert lock_path.name.lower() in dockerfile, "Dockerfile must COPY the authoritative lock"
    frozen_install = (
        re.search(r"pip(?:3)?\s+install[^\n]*--require-hashes[^\n]*\s-r\s", dockerfile)
        or re.search(r"uv\s+sync[^\n]*(?:--frozen|--locked)", dockerfile)
        or re.search(r"poetry\s+install[^\n]*--sync", dockerfile)
        or re.search(r"pdm\s+sync[^\n]*(?:--frozen-lockfile|--no-editable)", dockerfile)
    )
    assert frozen_install, "Dockerfile must install dependencies from the lock in frozen mode"


def test_build_dockerfile_provides_python_gdal_and_gate_toolchain():
    dockerfile = _read_required(DOCKERFILE_PATH, "build Dockerfile").lower()
    assert "python" in dockerfile, "Build image must provide Python"
    assert re.search(r"\b(?:gdal|osgeo)\b", dockerfile), "Build image must provide GDAL"
    lock_path = _lock_file()
    lock_content = _read_required(lock_path, "dependency lock").lower()
    for tool in ("pytest", "coverage", "ruff", "pyright", "pyyaml"):
        assert tool in lock_content, f"Build image lock must include {tool}"


def test_build_dockerfile_defines_no_source_gdb_capability():
    dockerfile = _read_required(DOCKERFILE_PATH, "build Dockerfile").lower()
    assert "indoorwayfinding.gdb" not in dockerfile
    assert not re.search(r"\bvolume\b[^\n]*(?:/data|\.gdb)", dockerfile)


def test_publish_workflow_exists_and_builds_smoke_tests_then_pushes_image():
    assert WORKFLOW_PATH.is_file(), "Missing .github/workflows/publish-build-image.yml"
    workflow = _read_required(WORKFLOW_PATH, "build-image publication workflow").lower()
    assert "infra/dockerfile.build" in workflow
    assert BUILD_IMAGE in workflow
    assert re.search(r"(?:docker\s+buildx?\s+build|docker/build-push-action)", workflow)
    assert "smoke" in workflow, (
        "Publish workflow must run smoke checks against the built image"
    )
    assert re.search(r"docker\s+run", workflow), (
        "Publish workflow must run smoke checks against the built image"
    )
    assert re.search(r"(?:push:\s*true|docker\s+push)", workflow), (
        "Publish workflow must push the validated image"
    )


def test_publish_workflow_exposes_digest_update_mechanism():
    workflow = _read_required(WORKFLOW_PATH, "build-image publication workflow").lower()
    assert "digest" in workflow, "Workflow must expose or record the published image digest"
    assert "infra/docker-compose.yml" in workflow, (
        "Workflow must record how the published digest updates normal Compose execution"
    )


def test_compose_services_share_exact_digest_pinned_image_without_build_fallback():
    services = _compose_services()
    expected = re.compile(rf"^{re.escape(BUILD_IMAGE)}@sha256:[0-9a-f]{{64}}$")
    artifact = services["artifact"]
    source_etl = services["source-etl"]
    assert expected.fullmatch(artifact.get("image", ""))
    assert source_etl.get("image") == artifact["image"]
    assert "build" not in artifact
    assert "build" not in source_etl


def test_gate_and_etl_capabilities_disable_external_networking():
    services = _compose_services()
    for name in ("artifact", "source-etl"):
        assert services[name].get("network_mode") == "none", name


def test_compose_artifact_mounts_repo_and_build_but_no_gdb_or_socket():
    services = _compose_services()
    artifact = services["artifact"]
    assert _mount_targets(artifact, "/workspace"), "artifact must mount the repository"
    assert _mount_targets(artifact, "/workspace/build"), "artifact must mount build read-write"
    rendered = yaml.safe_dump(_volume_entries(artifact)).lower()
    assert ".gdb" not in rendered
    assert "indoorwayfinding.gdb" not in rendered
    assert "docker.sock" not in rendered


def test_compose_source_etl_has_readonly_gdb_and_no_socket():
    services = _compose_services()
    source_etl = services["source-etl"]
    gdb_mounts = _mount_targets(source_etl, "/data/IndoorWayfinding.gdb")
    assert len(gdb_mounts) == 1, "source-etl must mount the source GDB exactly once"
    assert _mount_is_read_only(gdb_mounts[0]), "source-etl GDB mount must be read-only"
    assert _mount_targets(source_etl, "/workspace/build"), "source-etl must mount build read-write"
    assert "docker.sock" not in yaml.safe_dump(_volume_entries(source_etl)).lower()


@pytest.mark.parametrize("service_name", ["artifact", "source-etl", "demo"])
def test_compose_services_mask_workspace_data_with_readonly_tmpfs(service_name: str):
    services = _compose_services()
    entries = [_tmpfs_target_and_options(entry) for entry in _tmpfs_entries(services[service_name])]
    matching = [options for target, options in entries if target == "/workspace/data"]
    assert matching, f"{service_name} must mask /workspace/data with tmpfs"
    assert any(re.search(r"(?:^|,)\s*ro(?:\s*,|$)", options) for options in matching), (
        f"{service_name} /workspace/data tmpfs must include the ro option"
    )


def test_compose_source_etl_uses_repository_local_legacy_gdb_mount():
    source_etl = _compose_services()["source-etl"]
    mounts = _mount_targets(source_etl, "/data/IndoorWayfinding.gdb")
    assert any(
        isinstance(entry, str)
        and entry.replace("\\", "/").startswith(
            "../data/IndoorWayfinding.gdb:/data/IndoorWayfinding.gdb:ro"
        )
        for entry in mounts
    ), "source-etl must explicitly mount ../data/IndoorWayfinding.gdb read-only"


@pytest.mark.parametrize(
    ("target", "service"),
    [
        ("test", "artifact"),
        ("lint", "artifact"),
        ("type", "artifact"),
        ("dataqa", "artifact"),
        ("dataqa-source", "source-etl"),
        ("etl-extract", "source-etl"),
        ("etl-normalise", "artifact"),
        ("etl-graph-raw", "artifact"),
        ("etl-graph-transitions", "artifact"),
        ("etl-graph-contract", "artifact"),
    ],
)
def test_make_normal_target_uses_capability_service_and_pythonpath(target: str, service: str):
    recipes = _make_recipes()
    assert target in recipes, f"Makefile is missing the {target} recipe"
    recipe = recipes[target]
    assert re.search(rf"docker\s+compose\b.*\brun\s+--rm\s+{service}\b", recipe)
    assert "PYTHONPATH=/workspace/packages/wayfinding/src" in recipe


def test_make_normal_targets_contain_no_runtime_installers_or_failure_suppression():
    recipes = _make_recipes()
    normal_recipes = {
        target: recipe
        for target, recipe in recipes.items()
        if target not in {"image-build", "image-publish"}
    }
    assert normal_recipes, "Makefile must define normal containerized targets"
    for target, recipe in normal_recipes.items():
        assert not re.search(r"\b(?:apt|apt-get|pip|pip3|uv)\b", recipe.lower()), (
            f"{target} installs dependencies at target runtime"
        )
        assert "|| true" not in recipe, f"{target} must preserve non-zero gate failures"


def test_make_dataqa_selects_nonempty_strict_marker_suite():
    recipe = _make_recipes()["dataqa"]
    assert "pytest" in recipe
    assert re.search(r"(?:^|\s)-m(?:\s+|=)[\"']?dataqa", recipe)
    assert "--strict-markers" in recipe
    assert "--continue-on-collection-errors" not in recipe
    assert "--allow-no-tests" not in recipe
