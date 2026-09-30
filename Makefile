PYTHON ?= python3.11
ANALYTICS_FILES := 00_as_of 10_parts_consumption 11_inventory_health 12_tool_parts_risk \
	13_training_coverage 14_training_throughput 15_tool_readiness

.PHONY: up down schema seed reset venv psql analytics refresh export test check all lint

up:
	docker compose up -d --wait db

down:
	docker compose down

venv:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt

schema: up
	docker compose exec -T db psql -v ON_ERROR_STOP=1 -U fabtool -d fabtool -f /sql/01_schema.sql

seed: schema venv
	docker compose exec -T db psql -v ON_ERROR_STOP=1 -U fabtool -d fabtool -f /sql/02_seed_lookups.sql
	.venv/bin/python scripts/generate_data.py

reset:
	docker compose down -v
	$(MAKE) seed

analytics: up
	@for f in $(ANALYTICS_FILES); do \
		echo "==> sql/analytics/$$f.sql"; \
		docker compose exec -T db psql -v ON_ERROR_STOP=1 -U fabtool -d fabtool -f /sql/analytics/$$f.sql || exit 1; \
	done

refresh:
	docker compose exec -T db psql -v ON_ERROR_STOP=1 -U fabtool -d fabtool -f /sql/analytics/99_refresh.sql

export: analytics venv
	.venv/bin/python scripts/export_reports.py --site ALL --out exports

test: venv
	@if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest tests/ -v; else python -m pytest tests/ -v; fi

check:
	@if [ -x .venv/bin/python ]; then .venv/bin/python scripts/data_quality.py; else python scripts/data_quality.py; fi

all: analytics venv
	.venv/bin/python scripts/refresh_all.py

lint: venv
	.venv/bin/ruff check scripts tests

psql:
	docker compose exec db psql -U fabtool -d fabtool
