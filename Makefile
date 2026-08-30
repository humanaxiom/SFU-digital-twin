.PHONY: test lint type etl

test:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "apt-get update -qq && apt-get install -y --no-install-recommends docker.io docker-compose make -qq >/dev/null 2>&1 && pip install -e packages/wayfinding[dev] -q && pytest packages/wayfinding/tests"

lint:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "pip install -e packages/wayfinding[dev] && ruff check packages/wayfinding"

type:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "apt-get update -qq && apt-get install -y --no-install-recommends libatomic1 -qq >/dev/null && pip install -e packages/wayfinding[dev] && pyright packages/wayfinding/src"

etl:
	docker compose -f infra/docker-compose.yml run --rm etl sh -c "pip install -e packages/wayfinding[dev] && python -m wayfinding.etl.run"
