#!/bin/sh
# Run inside the immutable build image. No source dataset or build artifacts required.
set -eu
export PYTHONPATH=/workspace/packages/wayfinding/src
pytest packages/wayfinding/tests/test_smoke.py \
  packages/wayfinding/tests/test_dt002_etl_infrastructure.py \
  packages/wayfinding/tests/test_adr0006_hermetic_build.py \
  packages/wayfinding/tests/test_extract_synthetic.py \
  packages/wayfinding/tests/test_docker_evidence.py \
  packages/wayfinding/tests/test_docker_hook.py \
  packages/wayfinding/tests/test_takeover_http.py \
  packages/wayfinding/tests/test_takeover_client.py \
  packages/wayfinding/tests/test_dt018_guidance.py \
  packages/wayfinding/tests/test_dt018_client.py \
  packages/wayfinding/tests/test_rebuild.py \
  packages/wayfinding/tests/test_build_semantics.py \
  packages/wayfinding/tests/test_source_review.py \
  packages/wayfinding/tests/test_rebuild_infrastructure.py --no-cov
ruff check packages/wayfinding tools/capture_takeover_evidence.py tools/hooks/check_read_only_boundary.py
pyright packages/wayfinding/src
sh tests/gate/test_launch_stack.sh
sh tests/gate/test_no_host_python.sh
sh tests/gate/test_rebuild_launcher.sh
