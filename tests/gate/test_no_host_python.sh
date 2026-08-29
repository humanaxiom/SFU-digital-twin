#!/bin/sh
# Gate test: verify Makefile uses container-only execution (no bare python/pip/pytest).
#
# This script enforces .github/instructions/container-only-execution.instructions.md:
# every Python/pip/pytest invocation must be prefixed by "docker compose run --rm test"
# or equivalent, never run directly on the host.
#
# Runnable via: sh tests/gate/test_no_host_python.sh
# Also runnable via Git Bash on Windows.

set -e

MAKEFILE="Makefile"

# Check if Makefile exists
if [ ! -f "$MAKEFILE" ]; then
    echo "FAIL: Makefile does not exist yet"
    exit 1
fi

# Search for bare invocations of python, pip, or pytest that are NOT inside a docker compose command.
# Valid pattern:   docker compose run --rm test pytest ...
# Invalid pattern: pytest ... (bare invocation)
# 
# Strategy: grep for lines containing python/pip/pytest, then exclude lines that contain "docker compose"
BARE_INVOCATIONS=$(grep -E '\b(python|pip|pytest)\b' "$MAKEFILE" | grep -v "docker compose" || true)

if [ -n "$BARE_INVOCATIONS" ]; then
    echo "FAIL: Found bare python/pip/pytest invocations in Makefile (must use docker compose):"
    echo "$BARE_INVOCATIONS"
    exit 1
fi

echo "PASS: All python/pip/pytest invocations in Makefile use docker compose"
exit 0
