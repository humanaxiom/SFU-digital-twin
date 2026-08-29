.PHONY: test lint type

test:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "pip install -e packages/wayfinding[dev] && pytest packages/wayfinding/tests"

lint:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "pip install -e packages/wayfinding[dev] && ruff check packages/wayfinding"

type:
	docker compose -f infra/docker-compose.yml run --rm test sh -c "apt-get update -qq && apt-get install -y --no-install-recommends libatomic1 -qq >/dev/null && pip install -e packages/wayfinding[dev] && pyright packages/wayfinding/src"
