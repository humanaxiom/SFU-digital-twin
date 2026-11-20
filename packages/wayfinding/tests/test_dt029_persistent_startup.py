"""Persistent recovery contract for the existing protected public deployment."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("service", ["demo", "external"])
def test_public_services_recover_when_docker_restarts(service):
    config = yaml.safe_load((ROOT / "infra/docker-compose.candidate.yml").read_text())
    assert config["services"][service].get("restart") == "unless-stopped"
