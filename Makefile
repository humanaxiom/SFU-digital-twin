.PHONY: test lint type etl etl-extract etl-normalise etl-graph-raw

test:
	docker compose -f infra/docker-compose.yml run --rm etl sh -c "apt-get update -qq && apt-get install -y python3-pip -qq >/dev/null 2>&1 && pip install -e packages/wayfinding[dev] -q --break-system-packages && pytest packages/wayfinding/tests"

lint:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "pip install -e packages/wayfinding[dev] && ruff check packages/wayfinding"

type:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "apt-get update -qq && apt-get install -y --no-install-recommends libatomic1 -qq >/dev/null && pip install -e packages/wayfinding[dev] && pyright packages/wayfinding/src"

etl:
	docker compose -f infra/docker-compose.yml run --rm etl sh -c "pip install -e packages/wayfinding[dev] && python -m wayfinding.etl.run"

etl-extract:
	docker compose -f infra/docker-compose.yml run --rm etl sh -c "apt-get update -qq && apt-get install -y python3-pip -qq > /dev/null 2>&1 && pip install -e packages/wayfinding -q --break-system-packages && python -m wayfinding.etl.run extract"

etl-normalise:
	docker compose -f infra/docker-compose.yml run --rm etl sh -c "apt-get update -qq && apt-get install -y python3-pip python3-yaml -qq > /dev/null 2>&1 && pip install -e packages/wayfinding -q --break-system-packages && python -m wayfinding.etl.run normalise"

etl-graph-raw:
	docker compose -f infra/docker-compose.yml run --rm etl sh -c "apt-get update -qq && apt-get install -y python3-pip -qq > /dev/null 2>&1 && pip install -e packages/wayfinding -q --break-system-packages && python -m wayfinding.etl.run graph-raw"
