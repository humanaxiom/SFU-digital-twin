#!/bin/sh
# Container-only fault injection for the isolated public recovery Compose project.
set -eu
[ -f /.dockerenv ] || { echo 'Run recovery verification inside Docker.' >&2; exit 1; }
pid_file=/tmp/wayfinding-recovery-server.pid
case "${1:-}" in
    fail)
        read -r server_pid < "$pid_file"
        case "$server_pid" in ''|*[!0-9]*) exit 1 ;; esac
        [ "$server_pid" -gt 1 ] || exit 1
        kill -TERM "$server_pid"
        exit 0
        ;;
    start) ;;
    *) echo 'Usage: recovery-demo.sh start|fail' >&2; exit 2 ;;
esac
python -m wayfinding.demo.server --host 0.0.0.0 --port 8080 \
    --artifact /data/wayfinding.gpkg --graph /data/graph_contracted.pkl \
    --stats /data/graph_contracted_stats.json &
server_pid=$!
printf '%s\n' "$server_pid" > "$pid_file"
trap 'kill -TERM "$server_pid" 2>/dev/null || true' TERM INT
set +e
wait "$server_pid"
server_status=$?
exit "$server_status"
