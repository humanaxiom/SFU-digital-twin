"""Deployment contract for the user-confirmed WAN-to-LAN port mapping."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_public_deployment_targets_router_lan_port_and_private_candidate():
    settings = dict(
        line.split("=", 1)
        for line in (ROOT / "infra/wayfinding-public.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert settings["WAYFINDING_EXTERNAL_PORT"] == "18087"
    assert settings["WAYFINDING_EXTERNAL_BIND_ADDRESS"] == "0.0.0.0"
    assert settings["WAYFINDING_CANDIDATE_PORT"] == "18107"
    assert settings["WAYFINDING_CANDIDATE_BIND_ADDRESS"] == "127.0.0.1"
    assert settings["WAYFINDING_CANDIDATE_RUN"] == "sh-navigation-exact-20260923"
