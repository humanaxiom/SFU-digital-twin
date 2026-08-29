#!/bin/sh
# Gate test: verify source GDB is mounted read-only in all Docker services.
#
# This script enforces .github/copilot-instructions.md prime directive 1:
# the source geodatabase at C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb
# is read-only and must be mounted with :ro suffix in all container services.
#
# Runnable via: sh tests/gate/test_gdb_readonly.sh
# Also runnable via Git Bash on Windows.

set -e

COMPOSE_FILE="infra/docker-compose.yml"

# Check if docker-compose.yml exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "FAIL: infra/docker-compose.yml does not exist yet"
    exit 1
fi

# Find all volume lines that mention IndoorWayfinding.gdb
# Each should end with :ro (read-only mount)
GDB_MOUNTS=$(grep "IndoorWayfinding.gdb" "$COMPOSE_FILE" || true)

if [ -z "$GDB_MOUNTS" ]; then
    echo "FAIL: No IndoorWayfinding.gdb mounts found in $COMPOSE_FILE"
    exit 1
fi

# Check that every GDB mount line ends with :ro
# Strip leading/trailing whitespace, then check suffix
MISSING_RO=$(echo "$GDB_MOUNTS" | grep -v ":ro\s*$" || true)

if [ -n "$MISSING_RO" ]; then
    echo "FAIL: Found IndoorWayfinding.gdb mount(s) without :ro suffix:"
    echo "$MISSING_RO"
    exit 1
fi

echo "PASS: All IndoorWayfinding.gdb mounts in $COMPOSE_FILE have :ro suffix"
exit 0
