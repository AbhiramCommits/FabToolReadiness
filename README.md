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
make analytics                # create the analytics views (see sql/analytics/)
make export                   # Tableau CSVs + Excel tracker -> exports/
```

`make reset` builds the database from scratch and prints row counts per table at the end.
`make refresh` re-populates the materialized views in dependency order.
`python scripts/export_reports.py --site ALL --as-of YYYY-MM-DD --out exports/`
writes flat Tableau CSVs (`exports/tableau/`) and the formatted Excel tracker
(`exports/FabToolReadiness_Tracker.xlsx`) with KPI charts, a reorder tracker,
a training tracker, an at-risk tool list, and a data dictionary.

## Analytics views

| View | Grain |
|---|---|
| `v_parts_consumption` | site x part x month |
| `v_inventory_health` | site x part |
| `v_tool_parts_risk` | tool |
| `v_training_coverage` | tool_type x site x shift |
| `v_training_throughput` | site x month |
| `v_tool_readiness` | tool |

`v_tool_readiness` combines parts risk and training risk into a 0-100 readiness
score per tool, banded as `critical` / `at_risk` / `watch` / `healthy`, with the
top contributing reason as text.

## Layout

- `docker-compose.yml` — Postgres 16 on host port 5433 (db `fabtool`, user `fabtool`)
- `sql/01_schema.sql` — tables, constraints, indexes
- `sql/02_seed_lookups.sql` — sites, parts, certifications
- `sql/analytics/` — versioned analytics views + `99_refresh.sql`
- `scripts/generate_data.py` — reproducible synthetic data (24 months)
- `Makefile` — `up`, `schema`, `seed`, `reset`, `analytics`, `refresh`, `psql`
