#!/usr/bin/env python3
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path("/workspace")
DOCKER_COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"

cmd = [
    "docker", "compose", "-f", str(DOCKER_COMPOSE_PATH), "run", "--rm", "etl",
    "ogrinfo", "-ro", "-sql",
    "SELECT DISTINCT USE_TYPE FROM Units_AQ_SH_ECC ORDER BY USE_TYPE",
    "/data/IndoorWayfinding.gdb"
]

print("Running command:", " ".join(cmd))
print("CWD:", WORKSPACE_ROOT)
print()

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    cwd=WORKSPACE_ROOT
)

print("Return code:", result.returncode)
print("\nSTDOUT (first 1000 chars):")
print(result.stdout[:1000])
print("\nSTDERR (first 1000 chars):")
print(result.stderr[:1000])
