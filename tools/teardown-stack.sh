#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="$SCRIPT_DIR/../infra/docker-compose.yml"
PROJECT_NAME=
LOCAL_IMAGE=0
VOLUMES=0
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: tools/teardown-stack.sh [options]

Options:
  --compose-file PATH  Compose file used to launch the stack
  --project-name NAME  Exact Compose project printed at startup
  --local-image        Include docker-compose.local.yml
  --volumes            Also remove named and anonymous volumes
  --dry-run            Print the teardown command without running it
  -h, --help           Show this help
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --compose-file) COMPOSE_FILE=$2; shift 2 ;;
        --project-name) PROJECT_NAME=$2; shift 2 ;;
        --local-image) LOCAL_IMAGE=1; shift ;;
        --volumes) VOLUMES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -n "$PROJECT_NAME" ] || {
    echo "--project-name is required; use the exact Compose project printed at startup." >&2
    exit 2
}
case "$PROJECT_NAME" in
    [a-z0-9]* ) ;;
    * ) echo "Project name must start with a lowercase letter or digit." >&2; exit 2 ;;
esac
case "$PROJECT_NAME" in
    *[!a-z0-9_-]* ) echo "Project name may contain only lowercase letters, digits, '_' and '-'." >&2; exit 2 ;;
esac

command -v docker >/dev/null 2>&1 || {
    echo "Docker CLI was not found on PATH." >&2
    exit 1
}
docker compose version >/dev/null 2>&1 || {
    echo "Docker Compose is unavailable. Start Docker and retry." >&2
    exit 1
}
[ -f "$COMPOSE_FILE" ] || {
    echo "Compose file not found: $COMPOSE_FILE" >&2
    exit 1
}

set -- -f "$COMPOSE_FILE"
if [ "$LOCAL_IMAGE" -eq 1 ]; then
    LOCAL_OVERRIDE=$(dirname -- "$COMPOSE_FILE")/docker-compose.local.yml
    [ -f "$LOCAL_OVERRIDE" ] || {
        echo "Local image override not found: $LOCAL_OVERRIDE" >&2
        exit 1
    }
    set -- "$@" -f "$LOCAL_OVERRIDE"
fi

echo "Compose project: $PROJECT_NAME"
if [ "$DRY_RUN" -eq 1 ]; then
    printf 'Dry run: docker compose'
    printf ' %s' "$@"
    printf ' -p %s down --remove-orphans' "$PROJECT_NAME"
    [ "$VOLUMES" -eq 0 ] || printf ' --volumes'
    printf '\n'
    exit 0
fi

if [ "$VOLUMES" -eq 1 ]; then
    docker compose "$@" -p "$PROJECT_NAME" down --remove-orphans --volumes
else
    docker compose "$@" -p "$PROJECT_NAME" down --remove-orphans
fi
echo "Destroyed Compose project: $PROJECT_NAME"