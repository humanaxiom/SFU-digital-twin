#!/usr/bin/env python3
import os
import subprocess

print("PATH:", os.environ.get("PATH", "NOT SET"))
print("\nTrying to run 'which docker':")
result = subprocess.run(["which", "docker"], capture_output=True, text=True)
print(result.stdout)
print(result.stderr)

print("\nTrying to run 'docker --version':")
result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
print(result.stdout)
print(result.stderr)
print("Return code:", result.returncode)
