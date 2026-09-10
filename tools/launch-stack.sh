#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="$SCRIPT_DIR/../infra/docker-compose.yml"
BASE_PORT=18000
PROJECT_NAME=sfudt-wayfinding
ATTEMPTS=50
LOCAL_IMAGE=0
BUILD=0
TEST=0
DRY_RUN=0
PORT_BLOCK_SIZE=10

usage() {
    cat <<'EOF'
Usage: tools/launch-stack.sh [options]

Options:
  --compose-file PATH  Compose file to launch
  --base-port PORT     First candidate port block (default: 18000)
  --project-name NAME  Compose project prefix (default: sfudt-wayfinding)
  --attempts COUNT     Port blocks to scan (default: 50)
  --local-image        Include docker-compose.local.yml beside the Compose file
  --build              Build images before starting services
    --test               Run test, lint, type, and data-QA gates after startup
  --dry-run            Resolve configuration and print the launch command only
  -h, --help           Show this help
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --compose-file) COMPOSE_FILE=$2; shift 2 ;;
        --base-port) BASE_PORT=$2; shift 2 ;;
        --project-name) PROJECT_NAME=$2; shift 2 ;;
        --attempts) ATTEMPTS=$2; shift 2 ;;
        --local-image) LOCAL_IMAGE=1; shift ;;
        --build) BUILD=1; shift ;;
        --test) TEST=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$BASE_PORT:$ATTEMPTS" in
    *[!0-9:]*|:*|*:) echo "Base port and attempts must be positive integers." >&2; exit 2 ;;
esac
if [ "$BASE_PORT" -lt 1024 ] || [ "$BASE_PORT" -gt 65429 ] || [ "$ATTEMPTS" -lt 1 ]; then
    echo "Base port must be 1024-65429 and attempts must be at least 1." >&2
    exit 2
fi
case "$PROJECT_NAME" in
    [a-z0-9]* ) ;;
    * ) echo "Project name must start with a lowercase letter or digit." >&2; exit 2 ;;
esac
case "$PROJECT_NAME" in
    *[!a-z0-9_-]* ) echo "Project name may contain only lowercase letters, digits, '_' and '-'." >&2; exit 2 ;;
esac

command -v docker >/dev/null 2>&1 || { echo "Docker CLI was not found on PATH." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || {
    echo "Docker Compose is unavailable. Start Docker and retry." >&2
    exit 1
}
[ -f "$COMPOSE_FILE" ] || { echo "Compose file not found: $COMPOSE_FILE" >&2; exit 1; }

set -- -f "$COMPOSE_FILE"
compose_has_placeholder=0
if grep -q 'sha256:PUBLISHED_DIGEST_REQUIRED' "$COMPOSE_FILE"; then
    compose_has_placeholder=1
fi

use_local_image=$LOCAL_IMAGE
build_local_image=0
if [ "$BUILD" -eq 1 ] && [ "$use_local_image" -eq 0 ] && [ "$compose_has_placeholder" -eq 1 ]; then
    use_local_image=1
    build_local_image=1
    echo 'Detected unpublished build-image digest placeholder; enabling local image override for --build.'
fi

if [ "$use_local_image" -eq 1 ]; then
    LOCAL_OVERRIDE=$(dirname -- "$COMPOSE_FILE")/docker-compose.local.yml
    [ -f "$LOCAL_OVERRIDE" ] || { echo "Local image override not found: $LOCAL_OVERRIDE" >&2; exit 1; }
    set -- "$@" -f "$LOCAL_OVERRIDE"
fi

docker_ports=$(docker ps --format '{{.Ports}}')
port_is_free() {
    port=$1
    if printf '%s\n' "$docker_ports" | grep -Eq ":${port}->"; then
        return 1
    fi
    if command -v ss >/dev/null 2>&1; then
        ! ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
    elif command -v netstat >/dev/null 2>&1; then
        ! netstat -an 2>/dev/null | grep -E "[.:]${port}[[:space:]].*LISTEN" >/dev/null
    elif command -v lsof >/dev/null 2>&1; then
        ! lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | grep -q .
    else
        echo "Cannot check host ports: install ss, netstat, or lsof." >&2
        exit 1
    fi
}

selected_base=
attempt=0
while [ "$attempt" -lt "$ATTEMPTS" ]; do
    candidate=$((BASE_PORT + attempt * PORT_BLOCK_SIZE))
    if [ $((candidate + 7)) -gt 65535 ]; then
        break
    fi
    block_free=1
    offset=0
    while [ "$offset" -le 7 ]; do
        if ! port_is_free $((candidate + offset)); then
            block_free=0
            break
        fi
        offset=$((offset + 1))
    done
    if [ "$block_free" -eq 1 ]; then
        selected_base=$candidate
        break
    fi
    attempt=$((attempt + 1))
done

[ -n "$selected_base" ] || {
    echo "No free host-port block found after $ATTEMPTS attempts from port $BASE_PORT." >&2
    exit 1
}

export DTWIN_POSTGIS_HOST_PORT=$selected_base
export DTWIN_REDIS_HOST_PORT=$((selected_base + 1))
export DTWIN_MARTIN_HOST_PORT=$((selected_base + 2))
export DTWIN_API_HOST_PORT=$((selected_base + 3))
export DTWIN_WEB_HOST_PORT=$((selected_base + 4))
export DTWIN_NEO4J_HTTP_HOST_PORT=$((selected_base + 5))
export DTWIN_NEO4J_BOLT_HOST_PORT=$((selected_base + 6))
export DTWIN_DEMO_HOST_PORT=$((selected_base + 7))
selected_project="$PROJECT_NAME-$selected_base"

services=$(docker compose "$@" config --services)
[ -n "$services" ] || { echo "No services resolved from $COMPOSE_FILE." >&2; exit 1; }

print_gate_commands() {
    printf 'Dry run: docker compose'
    printf ' %s' "$@"
    printf ' -p %s exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests\n' "$selected_project"
    printf 'Dry run: docker compose'
    printf ' %s' "$@"
    printf ' -p %s exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src ruff check packages/wayfinding\n' "$selected_project"
    printf 'Dry run: docker compose'
    printf ' %s' "$@"
    printf ' -p %s exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src pyright packages/wayfinding/src\n' "$selected_project"
    printf 'Dry run: docker compose'
    printf ' %s' "$@"
    printf ' -p %s exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m dataqa --strict-markers\n' "$selected_project"
}

printf '%-28s %s\n' \
    'Compose project:' "$selected_project" \
    'Compose file:' "$COMPOSE_FILE" \
    'DTWIN_POSTGIS_HOST_PORT' "$DTWIN_POSTGIS_HOST_PORT" \
    'DTWIN_REDIS_HOST_PORT' "$DTWIN_REDIS_HOST_PORT" \
    'DTWIN_MARTIN_HOST_PORT' "$DTWIN_MARTIN_HOST_PORT" \
    'DTWIN_API_HOST_PORT' "$DTWIN_API_HOST_PORT" \
    'DTWIN_WEB_HOST_PORT' "$DTWIN_WEB_HOST_PORT" \
    'DTWIN_NEO4J_HTTP_HOST_PORT' "$DTWIN_NEO4J_HTTP_HOST_PORT" \
    'DTWIN_NEO4J_BOLT_HOST_PORT' "$DTWIN_NEO4J_BOLT_HOST_PORT" \
    'DTWIN_DEMO_HOST_PORT' "$DTWIN_DEMO_HOST_PORT" \
    'Demo URL' "http://127.0.0.1:$DTWIN_DEMO_HOST_PORT/"

if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$build_local_image" -eq 1 ]; then
        compose_dir=$(dirname -- "$COMPOSE_FILE")
        dockerfile="$compose_dir/Dockerfile.build"
        context_dir=$(CDPATH= cd -- "$compose_dir/.." && pwd)
        printf 'Dry run: docker build -f %s -t wayfinding-build:local %s\n' "$dockerfile" "$context_dir"
    fi
    printf 'Dry run: docker compose'
    printf ' %s' "$@"
    printf ' -p %s up -d --wait' "$selected_project"
    [ "$BUILD" -eq 0 ] || printf ' --build'
    printf '\n'
    [ "$TEST" -eq 0 ] || print_gate_commands "$@"
    exit 0
fi

if [ "$build_local_image" -eq 1 ]; then
    compose_dir=$(dirname -- "$COMPOSE_FILE")
    dockerfile="$compose_dir/Dockerfile.build"
    [ -f "$dockerfile" ] || { echo "Build file not found: $dockerfile" >&2; exit 1; }
    context_dir=$(CDPATH= cd -- "$compose_dir/.." && pwd)
    docker build -f "$dockerfile" -t wayfinding-build:local "$context_dir"
fi

if [ "$BUILD" -eq 1 ]; then
    docker compose "$@" -p "$selected_project" up -d --wait --build
else
    docker compose "$@" -p "$selected_project" up -d --wait
fi
docker compose "$@" -p "$selected_project" ps

if [ "$TEST" -eq 1 ]; then
    echo 'Running test gate...'
    docker compose "$@" -p "$selected_project" exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests
    echo 'Running lint gate...'
    docker compose "$@" -p "$selected_project" exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src ruff check packages/wayfinding
    echo 'Running type gate...'
    docker compose "$@" -p "$selected_project" exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src pyright packages/wayfinding/src
    echo 'Running dataqa gate...'
    docker compose "$@" -p "$selected_project" exec -T artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m dataqa --strict-markers
fi