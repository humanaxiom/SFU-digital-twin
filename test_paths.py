import pytest
from pathlib import Path

# This mirrors the test file's setup
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
DOCKER_COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"

def test_paths():
    """Test that workspace paths are correct."""
    print(f"__file__: {__file__}")
    print(f"WORKSPACE_ROOT: {WORKSPACE_ROOT}")
    print(f"WORKSPACE_ROOT.absolute(): {WORKSPACE_ROOT.absolute()}")
    print(f"WORKSPACE_ROOT.exists(): {WORKSPACE_ROOT.exists()}")
    print(f"DOCKER_COMPOSE_PATH: {DOCKER_COMPOSE_PATH}")
    print(f"DOCKER_COMPOSE_PATH.exists(): {DOCKER_COMPOSE_PATH.exists()}")
    assert WORKSPACE_ROOT.exists(), f"WORKSPACE_ROOT does not exist: {WORKSPACE_ROOT}"
    assert DOCKER_COMPOSE_PATH.exists(), f"DOCKER_COMPOSE_PATH does not exist: {DOCKER_COMPOSE_PATH}"
