#!/usr/bin/env python3
"""Post-load data quality checks for fabtoolreadiness.

Scans every foreign key in the current schema for orphans, then runs a set
of domain invariant checks (negative on-hand, BOM parts missing from parts,
certifications expiring before they were earned, duplicate movement IDs,
tools with no BOM). Prints a pass/fail table and exits non-zero if any
check finds violating rows.

Usage:
    python scripts/data_quality.py
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


def _read_env_file() -> dict:
    env = {}
    path = Path(__file__).resolve().parent.parent / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def connect():
    file_env = _read_env_file()

    def val(key, default):
        return os.environ.get(key) or file_env.get(key) or default

    url = (f"postgresql+psycopg2://{val('FABTOOL_DB_USER', 'fabtool')}"
           f":{val('POSTGRES_PASSWORD', '')}"
           f"@{val('FABTOOL_DB_HOST', 'localhost')}"
           f":{val('FABTOOL_DB_PORT', '5433')}"
           f"/{val('FABTOOL_DB_NAME', 'fabtool')}")
    return create_engine(url)


FK_CATALOG = """
SELECT tc.table_name AS tbl,
       kcu.column_name AS col,
       ccu.table_name AS ref_tbl,
       ccu.column_name AS ref_col
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name
 AND kcu.constraint_schema = tc.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.constraint_schema = tc.table_schema
JOIN information_schema.referential_constraints rc
  ON rc.constraint_name = tc.constraint_name
 AND rc.constraint_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = current_schema()
ORDER BY tc.table_name, kcu.column_name
"""

FIXED_CHECKS = [
    ("inventory.on_hand_qty >= 0",
     "SELECT COUNT(*) FROM inventory WHERE on_hand_qty < 0"),
    ("tool_bom.part_id exists in parts",
     "SELECT COUNT(*) FROM tool_bom b "
     "LEFT JOIN parts p ON p.part_id = b.part_id WHERE p.part_id IS NULL"),
    ("tech_certifications.expires_date > earned_date",
     "SELECT COUNT(*) FROM tech_certifications "
     "WHERE earned_date IS NOT NULL AND expires_date IS NOT NULL "
     "AND expires_date <= earned_date"),
    ("stock_movements.movement_id unique",
     "SELECT COUNT(*) FROM (SELECT movement_id FROM stock_movements "
     "GROUP BY movement_id HAVING COUNT(*) > 1) d"),
    ("every tool has at least one BOM part",
     "SELECT COUNT(*) FROM tools t "
     "LEFT JOIN tool_bom b ON b.tool_id = t.tool_id WHERE b.tool_id IS NULL"),
]


def main():
    engine = connect()
    checks = []

    with engine.connect() as conn:
        for fk in conn.execute(text(FK_CATALOG)).mappings():
            name = (f"FK: {fk['tbl']}.{fk['col']} "
                    f"-> {fk['ref_tbl']}.{fk['ref_col']}")
            sql = text(f"""
                SELECT COUNT(*) FROM {fk['tbl']} t
                LEFT JOIN {fk['ref_tbl']} r
                       ON t.{fk['col']} = r.{fk['ref_col']}
                WHERE t.{fk['col']} IS NOT NULL AND r.{fk['ref_col']} IS NULL
            """)
            checks.append((name, conn.execute(sql).scalar()))

        for name, sql in FIXED_CHECKS:
            checks.append((name, conn.execute(text(sql)).scalar()))

    width = max(len(n) for n, _ in checks) + 2
    print(f"{'Data quality check':<{width}} {'Status':<7} Violations")
    print("-" * (width + 20))
    failed = 0
    for name, violations in checks:
        status = "PASS" if violations == 0 else "FAIL"
        if violations:
            failed += 1
        print(f"{name:<{width}} {status:<7} {violations}")
    print("-" * (width + 20))
    print(f"TOTAL: {len(checks)} checks, {len(checks) - failed} passed, "
          f"{failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
