"""Guard Windows PowerShell's parameter-time script-root limitation.

Actual Windows startup is exercised as thin Docker launcher glue; these
container-run checks prevent reintroducing a default that fails before the body.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("name", ["launch-stack.ps1", "teardown-stack.ps1"])
def test_compose_default_does_not_use_script_root_during_parameter_binding(name):
    source = (ROOT / "tools" / name).read_text(encoding="utf-8")
    parameters, body = source.split("$ErrorActionPreference = 'Stop'", 1)
    assert "$PSScriptRoot" not in parameters
    assert "Join-Path $PSScriptRoot" in body
