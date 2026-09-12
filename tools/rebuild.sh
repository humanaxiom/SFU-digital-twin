#!/usr/bin/env bash
set -eu

usage() { echo "usage: $0 build|review|compare RUN_ID [OTHER_RUN_ID] [--local-image] [--topology endpoint-v1|exact-shared-vertices-v1]" >&2; exit 2; }
[ "$#" -ge 2 ] || usage
action=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]'); run_id=$2; shift 2
other_id=""; local_image=0; topology="endpoint-v1"; topology_set=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --local-image) local_image=1 ;;
    --topology) [ "$topology_set" -eq 0 ] || usage; [ "$#" -ge 2 ] || usage; topology=$2; topology_set=1; shift ;;
    *) [ -z "$other_id" ] || usage; other_id=$1 ;;
  esac
  shift
done
case "$action" in build|review|compare) ;; *) usage ;; esac
[ "$topology" = endpoint-v1 ] || [ "$topology" = exact-shared-vertices-v1 ] || usage
[ "$action" = build ] || [ "$topology_set" -eq 0 ] || usage
case "$run_id" in ''|*[!A-Za-z0-9_-]*) usage ;; esac
case "$run_id" in [!A-Za-z0-9]*) usage ;; esac
[ "${#run_id}" -le 64 ] || usage
if [ "$action" = compare ]; then
  [ -n "$other_id" ] || usage
  case "$other_id" in ''|*[!A-Za-z0-9_-]*) usage ;; esac
  case "$other_id" in [!A-Za-z0-9]*) usage ;; esac
  [ "${#other_id}" -le 64 ] || usage
  [ "$(printf '%s' "$run_id" | tr '[:upper:]' '[:lower:]')" != "$(printf '%s' "$other_id" | tr '[:upper:]' '[:lower:]')" ] || usage
elif [ -n "$other_id" ]; then usage; fi

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file=$root_dir/infra/docker-compose.rebuild.yml
project="sfudt-rebuild-$(printf '%s' "$run_id" | tr '[:upper:]' '[:lower:]')"
if [ "$local_image" -eq 1 ]; then image_ref=wayfinding-build:local; else image_ref=ghcr.io/humanaxiom/sfu-digital-twin/wayfinding-build@sha256:26259879732ceffe8405f22d19c423bf14408583e1a752da35a61d3e2825276c; fi
if ! image_id=$(docker image inspect "$image_ref" --format '{{.Id}}'); then
  if [ "$local_image" -eq 1 ]; then
    echo "Could not inspect local image '$image_ref'; see the Docker diagnostic above. If it is missing, build it with: docker build -f infra/Dockerfile.build -t wayfinding-build:local ." >&2
  else
    echo "Could not inspect published image '$image_ref'; see the Docker diagnostic above. To use an existing local development image, re-run with --local-image. If wayfinding-build:local is also missing, build it from the repository root with: docker build -f infra/Dockerfile.build -t wayfinding-build:local ." >&2
  fi
  exit 1
fi
image_hex=${image_id#sha256:}
if [ "$image_id" = "$image_hex" ] || [ "${#image_hex}" -ne 64 ]; then echo "Selected image '$image_ref' returned an invalid immutable ID; check the Docker image inspect output." >&2; exit 1; fi
case "$image_hex" in *[!0-9a-fA-F]*) echo "Selected image '$image_ref' returned an invalid immutable ID; check the Docker image inspect output." >&2; exit 1 ;; esac
old_id=${WAYFINDING_BUILD_IMAGE_ID-}; old_ref=${WAYFINDING_BUILD_IMAGE_REFERENCE-}; old_image=${WAYFINDING_REBUILD_IMAGE-}
restore() { if [ -n "${old_id+x}" ]; then export WAYFINDING_BUILD_IMAGE_ID=$old_id; else unset WAYFINDING_BUILD_IMAGE_ID; fi; if [ -n "${old_ref+x}" ]; then export WAYFINDING_BUILD_IMAGE_REFERENCE=$old_ref; else unset WAYFINDING_BUILD_IMAGE_REFERENCE; fi; if [ -n "${old_image+x}" ]; then export WAYFINDING_REBUILD_IMAGE=$old_image; else unset WAYFINDING_REBUILD_IMAGE; fi; }
trap restore EXIT
export WAYFINDING_REBUILD_IMAGE=$image_id WAYFINDING_BUILD_IMAGE_ID=$image_id WAYFINDING_BUILD_IMAGE_REFERENCE=$image_ref
run() { docker compose -p "$project" -f "$compose_file" run --rm --no-deps -T "$@"; }
case "$action" in
  build) if [ "$topology" = endpoint-v1 ]; then run source-build python -m wayfinding.etl.rebuild extract --run-id "$run_id"; else run source-build python -m wayfinding.etl.rebuild extract --run-id "$run_id" --topology "$topology"; fi; run artifact-build python -m wayfinding.etl.rebuild derive --run-id "$run_id"; run source-build python -m wayfinding.etl.rebuild finalize --run-id "$run_id" ;;
  review) run source-review python -m wayfinding.etl.source_review --legacy /sources/IndoorWayfinding.gdb --revised /sources/IndoorWayfinding_AQ_SH_ECC_Revised.gdb --supplemental /sources/AdditionalData_Testing.gdb --output "/workspace/build/experiments/reviews/$run_id.json" ;;
  compare) run artifact-build python -m wayfinding.etl.rebuild compare --left "$run_id" --right "$other_id" ;;
esac
