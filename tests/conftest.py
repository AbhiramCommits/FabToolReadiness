"""Shared pytest fixtures: a throwaway Postgres schema seeded with the
deterministic fixture (tests/fixture_seed.sql), with the full analytics view
stack applied and the fabtool.as_of GUC pinned to a fixed date.

The test database connection is resolved like everywhere else in the repo:
FABTOOL_DB_* / POSTGRES_PASSWORD env vars first, .env file second.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "pytest_fabtool"
AS_OF = "2026-01-15"

ANALYTICS_FILES = [
    "10_parts_consumption.sql",
    "11_inventory_health.sql",
    "12_tool_parts_risk.sql",
    "13_training_coverage.sql",
    "14_training_throughput.sql",
    "15_tool_readiness.sql",
]
MATVIEWS = ["v_inventory_health", "v_tool_parts_risk",
            "v_training_coverage", "v_tool_readiness"]


def _read_env_file() -> dict:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def db_url() -> str:
    file_env = _read_env_file()

    def val(key, default):
        return os.environ.get(key) or file_env.get(key) or default

    return (f"postgresql+psycopg2://{val('FABTOOL_DB_USER', 'fabtool')}"
            f":{val('POSTGRES_PASSWORD', '')}"
            f"@{val('FABTOOL_DB_HOST', 'localhost')}"
            f":{val('FABTOOL_DB_PORT', '5433')}"
            f"/{val('FABTOOL_DB_NAME', 'fabtool')}")


@pytest.fixture(scope="session")
def engine():
    """Engine bound to the throwaway schema with as-of pinned to AS_OF."""
    admin = create_engine(db_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))

    options = f"-c search_path={SCHEMA} -c fabtool.as_of={AS_OF}"
    eng = create_engine(db_url(), connect_args={"options": options})
    with eng.begin() as conn:
        conn.execute(text((ROOT / "sql" / "01_schema.sql").read_text()))
        conn.execute(text((ROOT / "sql" / "analytics" / "00_as_of.sql").read_text()))
        for name in ANALYTICS_FILES:
            conn.execute(text((ROOT / "sql" / "analytics" / name).read_text()))
        conn.execute(text((ROOT / "tests" / "fixture_seed.sql").read_text()))
        for mv in MATVIEWS:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {mv}"))

    yield eng

    with admin.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    admin.dispose()
