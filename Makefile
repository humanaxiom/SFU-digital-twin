.PHONY: image-build test dt014 dt015 dt015-evidence test-launchers lint type dataqa dataqa-source etl etl-extract etl-normalise etl-graph-raw etl-graph-transitions etl-graph-contract

COMPOSE_FILES ?= -f infra/docker-compose.yml
RUN_ID ?=
OTHER_RUN_ID ?=
REBUILD_OPTIONS ?=

.PHONY: rebuild source-review compare-builds
rebuild:
	sh tools/rebuild.sh build "$(RUN_ID)" $(REBUILD_OPTIONS)

source-review:
	sh tools/rebuild.sh review "$(RUN_ID)" $(REBUILD_OPTIONS)

compare-builds:
	sh tools/rebuild.sh compare "$(RUN_ID)" "$(OTHER_RUN_ID)" $(REBUILD_OPTIONS)

.PHONY: gates fast browser
fast:
	docker compose $(COMPOSE_FILES) run --rm artifact sh tools/check-fast.sh

browser:
	docker compose -f infra/docker-compose.browser.yml up --force-recreate --abort-on-container-exit --exit-code-from browser

gates:
	$(MAKE) test
	$(MAKE) lint
	$(MAKE) type
	$(MAKE) dataqa

image-build:
	docker build -f infra/Dockerfile.build -t wayfinding-build:local .

test:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests

dt014:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests/test_dt014_routing.py packages/wayfinding/tests/test_dt014_static_client.py packages/wayfinding/tests/test_dt014_demo_deployment.py --no-cov

dt015:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests/test_dt015_demo_deployment.py packages/wayfinding/tests/test_dt015_static_client.py packages/wayfinding/tests/test_dt015_evidence.py --no-cov

dt015-evidence:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.demo.evidence

test-launchers:
	docker compose $(COMPOSE_FILES) run --rm artifact sh tests/gate/test_launch_stack.sh

lint:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src ruff check packages/wayfinding

type:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pyright packages/wayfinding/src

dataqa:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m dataqa --strict-markers --no-cov

dataqa-source:
	docker compose $(COMPOSE_FILES) run --rm source-etl sh -c 'if ! test -d /data/IndoorWayfinding.gdb; then echo "Required read-only source GDB is unavailable" >&2; exit 1; fi; exec env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m source_dataqa --strict-markers --no-cov'

etl: rebuild

etl-extract:
	docker compose $(COMPOSE_FILES) run --rm source-etl env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.etl.run extract

etl-normalise:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.etl.run normalise

etl-graph-raw:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.etl.run graph-raw

etl-graph-transitions:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.etl.run graph-transitions

etl-graph-contract:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.etl.run graph-contract
