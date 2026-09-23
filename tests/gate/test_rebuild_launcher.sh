#!/usr/bin/env bash
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/docker" <<'EOF'
#!/usr/bin/env bash
set -eu
if [ "${FAKE_MISSING:-0}" = 1 ] && [ "$1" = image ] && [ "$2" = inspect ]; then exit 1; fi
if [ "$1" = image ] && [ "$2" = inspect ]; then echo "${FAKE_IMAGE_ID:-sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}"; exit 0; fi
printf '%s\n' "$*" >> "$FAKE_LOG"
printf 'IMAGE=%s ID=%s REF=%s\n' "${WAYFINDING_REBUILD_IMAGE-}" "${WAYFINDING_BUILD_IMAGE_ID-}" "${WAYFINDING_BUILD_IMAGE_REFERENCE-}" >> "$FAKE_LOG"
if [ -n "${FAKE_FAIL:-}" ] && [[ "$*" == *"$FAKE_FAIL"* ]]; then exit 9; fi
EOF
chmod +x "$tmp/docker"
export PATH="$tmp:$PATH" FAKE_LOG="$tmp/log"
sh "$root/tools/rebuild.sh" build Run_01 --local-image
grep -q 'run --rm --no-deps -T source-build python -m wayfinding.etl.rebuild extract --run-id Run_01' "$FAKE_LOG"
grep -q 'run --rm --no-deps -T artifact-build python -m wayfinding.etl.rebuild derive --run-id Run_01' "$FAKE_LOG"
grep -q 'run --rm --no-deps -T source-build python -m wayfinding.etl.rebuild finalize --run-id Run_01' "$FAKE_LOG"
grep -q 'IMAGE=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ID=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa REF=wayfinding-build:local' "$FAKE_LOG"
if grep -q -- '--topology' "$FAKE_LOG"; then exit 1; fi
:
sh "$root/tools/rebuild.sh" build Run_02 --topology exact-shared-vertices-v1 --local-image
grep -q 'extract --run-id Run_02 --topology exact-shared-vertices-v1' "$FAKE_LOG"
sh "$root/tools/rebuild.sh" build Run_03 --topology endpoint-v1 --local-image
grep -q 'extract --run-id Run_03 --topology endpoint-v1' "$FAKE_LOG"
if sh "$root/tools/rebuild.sh" review Review_02 --topology endpoint-v1 --local-image >/dev/null 2>&1; then exit 1; fi
if sh "$root/tools/rebuild.sh" build BadTopology --topology invalid --local-image >/dev/null 2>&1; then exit 1; fi
if sh "$root/tools/rebuild.sh" compare Same same >/dev/null 2>&1; then exit 1; fi
if sh "$root/tools/rebuild.sh" build bad.id >/dev/null 2>&1; then exit 1; fi
if FAKE_IMAGE_ID=sha256:gggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggg sh "$root/tools/rebuild.sh" build BadImage --local-image >/dev/null 2>&1; then exit 1; fi
if output=$(FAKE_MISSING=1 sh "$root/tools/rebuild.sh" build MissingImage --local-image 2>&1); then exit 1; fi
echo "$output" | grep -q -- "docker build -f infra/Dockerfile.build -t wayfinding-build:local ."
if output=$(FAKE_MISSING=1 sh "$root/tools/rebuild.sh" build MissingPublished 2>&1); then exit 1; fi
echo "$output" | grep -q -- "--local-image"
: >"$FAKE_LOG"
export FAKE_FAIL='extract --run-id Stop_01'
if sh "$root/tools/rebuild.sh" build Stop_01 --local-image >/dev/null 2>&1; then exit 1; fi
if grep -q 'derive --run-id Stop_01' "$FAKE_LOG"; then exit 1; fi
unset FAKE_FAIL
: >"$FAKE_LOG"
sh "$root/tools/rebuild.sh" review Review_01 --local-image
grep -q 'source-review.*--output /workspace/build/experiments/reviews/Review_01.json' "$FAKE_LOG"
: >"$FAKE_LOG"
sh "$root/tools/rebuild.sh" compare Left_01 Right_01 --local-image
grep -q 'compare --left Left_01 --right Right_01' "$FAKE_LOG"
: >"$FAKE_LOG"
export FAKE_FAIL='derive --run-id Stop_02'
if sh "$root/tools/rebuild.sh" build Stop_02 --local-image >/dev/null 2>&1; then exit 1; fi
if grep -q 'finalize --run-id Stop_02' "$FAKE_LOG"; then exit 1; fi
