#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
LAUNCHER="$ROOT_DIR/tools/launch-stack.sh"
POWERSHELL_LAUNCHER="$ROOT_DIR/tools/launch-stack.ps1"
TEARDOWN="$ROOT_DIR/tools/teardown-stack.sh"
POWERSHELL_TEARDOWN="$ROOT_DIR/tools/teardown-stack.ps1"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
DOCKER_LOG="$TMP_DIR/docker.log"
export DOCKER_LOG

cat > "$TMP_DIR/docker" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "$*" in
    "compose version") exit 0 ;;
    "ps --format {{.Ports}}") printf '%s\n' "${FAKE_DOCKER_PORTS:-}" ;;
    *"config --services") echo fixture ;;
    *"up -d --wait"*) exit 0 ;;
    *" down --remove-orphans"*) exit 0 ;;
    *" exec -T artifact "*)
        case "$*" in
            *" pytest packages/wayfinding/tests -m dataqa "*) gate=dataqa ;;
            *" pytest packages/wayfinding/tests") gate=test ;;
            *" ruff check packages/wayfinding") gate=lint ;;
            *" pyright packages/wayfinding/src") gate=type ;;
            *) gate=unknown ;;
        esac
        if [ "${FAKE_FAIL_GATE:-}" = "$gate" ]; then
            exit "${FAKE_GATE_EXIT:-23}"
        fi
        exit 0
        ;;
    *" ps") exit 0 ;;
    *) echo "Unexpected fake Docker invocation: $*" >&2; exit 1 ;;
esac
EOF

cat > "$TMP_DIR/ss" <<'EOF'
#!/bin/sh
if [ "${FAKE_ALL_PORTS_BUSY:-0}" = 1 ]; then
    echo LISTEN
    exit 0
fi
case " ${FAKE_BUSY_PORTS:-} " in
    *" ${3##*:} "*) echo LISTEN ;;
esac
EOF
chmod +x "$TMP_DIR/docker" "$TMP_DIR/ss"

run_launcher() {
    PATH="$TMP_DIR:$PATH" "$LAUNCHER" --compose-file "$ROOT_DIR/infra/docker-compose.yml" "$@"
}

assert_contains() {
    output=$1
    expected=$2
    printf '%s\n' "$output" | grep -F "$expected" >/dev/null || {
        echo "FAIL: expected output to contain: $expected" >&2
        exit 1
    }
}

output=$(FAKE_DOCKER_PORTS='0.0.0.0:18000->5432/tcp' run_launcher --dry-run)
assert_contains "$output" 'Compose project:             sfudt-wayfinding-18010'
assert_contains "$output" 'DTWIN_NEO4J_BOLT_HOST_PORT   18016'

output=$(FAKE_BUSY_PORTS='18100' run_launcher --base-port 18100 --dry-run)
assert_contains "$output" 'Compose project:             sfudt-wayfinding-18110'

if FAKE_ALL_PORTS_BUSY=1 run_launcher --base-port 65429 --attempts 100 --dry-run >"$TMP_DIR/exhaustion.out" 2>&1; then
    echo 'FAIL: expected upper-bound port exhaustion' >&2
    exit 1
fi
grep -F 'No free host-port block found after 100 attempts from port 65429.' "$TMP_DIR/exhaustion.out" >/dev/null

if run_launcher --project-name Invalid --dry-run >"$TMP_DIR/invalid.out" 2>&1; then
    echo 'FAIL: expected invalid project name to be rejected' >&2
    exit 1
fi

: > "$DOCKER_LOG"
run_launcher --test >/dev/null
for command in \
    'pytest packages/wayfinding/tests' \
    'ruff check packages/wayfinding' \
    'pyright packages/wayfinding/src' \
    'pytest packages/wayfinding/tests -m dataqa --strict-markers'
do
    grep -F "exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src $command" "$DOCKER_LOG" >/dev/null || {
        echo "FAIL: POSIX launcher did not run gate: $command" >&2
        exit 1
    }
    grep -F "$command" "$POWERSHELL_LAUNCHER" >/dev/null || {
        echo "FAIL: PowerShell launcher is missing gate: $command" >&2
        exit 1
    }
done

grep -F '[switch]$Test' "$POWERSHELL_LAUNCHER" >/dev/null || {
    echo 'FAIL: PowerShell launcher is missing -Test' >&2
    exit 1
}
grep -F -- '--test' "$LAUNCHER" >/dev/null || {
    echo 'FAIL: POSIX launcher is missing --test' >&2
    exit 1
}
grep -F 'exit $gateExitCode' "$POWERSHELL_LAUNCHER" >/dev/null || {
    echo 'FAIL: PowerShell launcher does not preserve a failing gate exit code' >&2
    exit 1
}

: > "$DOCKER_LOG"
set +e
FAKE_FAIL_GATE=lint FAKE_GATE_EXIT=23 run_launcher --test >/dev/null 2>&1
failure_status=$?
set -e
[ "$failure_status" -eq 23 ] || {
    echo "FAIL: expected gate exit code 23, got $failure_status" >&2
    exit 1
}
grep -F 'ruff check packages/wayfinding' "$DOCKER_LOG" >/dev/null || {
    echo 'FAIL: failing lint gate was not invoked' >&2
    exit 1
}
if grep -F 'pyright packages/wayfinding/src' "$DOCKER_LOG" >/dev/null; then
    echo 'FAIL: launcher did not stop after the failing lint gate' >&2
    exit 1
fi

[ -x "$TEARDOWN" ] || {
    echo 'FAIL: POSIX teardown script is missing or not executable' >&2
    exit 1
}
[ -f "$POWERSHELL_TEARDOWN" ] || {
    echo 'FAIL: PowerShell teardown script is missing' >&2
    exit 1
}

: > "$DOCKER_LOG"
if PATH="$TMP_DIR:$PATH" "$TEARDOWN" \
    --compose-file "$ROOT_DIR/infra/docker-compose.yml" >"$TMP_DIR/teardown-missing.out" 2>&1
then
    echo 'FAIL: teardown accepted a missing project name' >&2
    exit 1
fi
grep -F -- '--project-name is required' "$TMP_DIR/teardown-missing.out" >/dev/null
if grep -F ' down ' "$DOCKER_LOG" >/dev/null; then
    echo 'FAIL: teardown invoked Compose down without a project name' >&2
    exit 1
fi

: > "$DOCKER_LOG"
PATH="$TMP_DIR:$PATH" "$TEARDOWN" \
    --compose-file "$ROOT_DIR/infra/docker-compose.yml" \
    --project-name sfudt-wayfinding-18010 \
    --local-image
grep -F 'compose -f' "$DOCKER_LOG" | grep -F -- \
    '-p sfudt-wayfinding-18010 down --remove-orphans' >/dev/null || {
    echo 'FAIL: teardown is not scoped to the requested Compose project' >&2
    exit 1
}
grep -F 'docker-compose.local.yml' "$DOCKER_LOG" >/dev/null || {
    echo 'FAIL: teardown did not include the local image override' >&2
    exit 1
}
if grep -F -- 'down --remove-orphans --volumes' "$DOCKER_LOG" >/dev/null; then
    echo 'FAIL: teardown removed volumes without --volumes' >&2
    exit 1
fi

: > "$DOCKER_LOG"
PATH="$TMP_DIR:$PATH" "$TEARDOWN" \
    --compose-file "$ROOT_DIR/infra/docker-compose.yml" \
    --project-name sfudt-wayfinding-18010 \
    --volumes
grep -F -- 'down --remove-orphans --volumes' "$DOCKER_LOG" >/dev/null || {
    echo 'FAIL: teardown did not explicitly request volume removal' >&2
    exit 1
}

for contract in '[Parameter(Mandatory)]' "[string]\$ProjectName" "[switch]\$LocalImage" \
    "[switch]\$Volumes" 'down' '--remove-orphans'
do
    grep -F -- "$contract" "$POWERSHELL_TEARDOWN" >/dev/null || {
        echo "FAIL: PowerShell teardown is missing contract: $contract" >&2
        exit 1
    }
done

grep -Eq 'command:.*sleep.*infinity' "$ROOT_DIR/infra/docker-compose.yml" || {
    echo 'FAIL: Compose services do not have a persistent command' >&2
    exit 1
}
grep -F 'healthcheck:' "$ROOT_DIR/infra/docker-compose.yml" >/dev/null || {
    echo 'FAIL: Compose services do not define a health check' >&2
    exit 1
}

for variable in \
    DTWIN_POSTGIS_HOST_PORT DTWIN_REDIS_HOST_PORT DTWIN_MARTIN_HOST_PORT \
    DTWIN_API_HOST_PORT DTWIN_WEB_HOST_PORT DTWIN_NEO4J_HTTP_HOST_PORT \
    DTWIN_NEO4J_BOLT_HOST_PORT
do
    grep -F "$variable" "$LAUNCHER" >/dev/null
    grep -F "$variable" "$POWERSHELL_LAUNCHER" >/dev/null
done

echo 'PASS: stack launchers share the isolated-port contract and handle collisions'