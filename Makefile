PYTHON ?= python3.11

.PHONY: up down schema seed reset venv psql

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

psql:
	docker compose exec db psql -U fabtool -d fabtool
