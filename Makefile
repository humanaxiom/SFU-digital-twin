.PHONY: image-build test test-launchers lint type dataqa dataqa-source etl etl-extract etl-normalise etl-graph-raw etl-graph-transitions etl-graph-contract

COMPOSE_FILES ?= -f infra/docker-compose.yml

image-build:
	docker build -f infra/Dockerfile.build -t wayfinding-build:local .

test:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests

test-launchers:
	docker compose $(COMPOSE_FILES) run --rm artifact sh tests/gate/test_launch_stack.sh

lint:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src ruff check packages/wayfinding

type:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pyright packages/wayfinding/src

dataqa:
	docker compose $(COMPOSE_FILES) run --rm artifact env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m dataqa --strict-markers

dataqa-source:
	docker compose $(COMPOSE_FILES) run --rm source-etl env PYTHONPATH=/workspace/packages/wayfinding/src pytest packages/wayfinding/tests -m source_dataqa --strict-markers

etl:
	docker compose $(COMPOSE_FILES) run --rm source-etl env PYTHONPATH=/workspace/packages/wayfinding/src python -m wayfinding.etl.run

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
