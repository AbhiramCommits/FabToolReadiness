# fabtoolreadiness

Semiconductor-fab operations analytics project: tracks spare-parts inventory and
technician training coverage per fab tool, to flag tools at risk of downtime.

## Stack

- PostgreSQL 16 (Docker Compose)
- Python 3.11 (pandas, SQLAlchemy, psycopg2-binary, Faker)
- No web framework

## Quickstart

```sh
cp .env.example .env          # set a real password
make reset                    # db up -> schema -> lookups -> synthetic data
```

`make reset` builds the database from scratch and prints row counts per table at the end.

## Layout

- `docker-compose.yml` — Postgres 16 on host port 5433 (db `fabtool`, user `fabtool`)
- `sql/01_schema.sql` — tables, constraints, indexes
- `sql/02_seed_lookups.sql` — sites, parts, certifications
- `scripts/generate_data.py` — reproducible synthetic data (24 months)
- `Makefile` — `up`, `schema`, `seed`, `reset`, `psql`
