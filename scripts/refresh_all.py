#!/usr/bin/env python3
"""One-command pipeline for fabtoolreadiness.

Runs the full delivery cycle in order:
  1. refresh the materialized views (dependency order),
  2. run the data quality checks (halt on failure),
  3. export the Tableau CSVs and the Excel tracker,
  4. regenerate the figures embedded in docs/FINDINGS.md from its template.

Usage:
    python scripts/refresh_all.py      # or `make all`
"""

import datetime as dt
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("refresh_all")

MATVIEWS = ["v_inventory_health", "v_tool_parts_risk",
            "v_training_coverage", "v_tool_readiness"]

FINDINGS_TEMPLATE = ROOT / "docs" / "FINDINGS.md.tmpl"
FINDINGS_OUT = ROOT / "docs" / "FINDINGS.md"

RISK_SQL = """
SELECT COUNT(*) AS total_tools,
       COUNT(*) FILTER (WHERE risk_band = 'critical') AS critical_count,
       COUNT(*) FILTER (WHERE risk_band = 'at_risk') AS at_risk_count
FROM v_tool_readiness
"""

STOCK_SQL = """
SELECT COUNT(*) AS total_bins,
       COUNT(*) FILTER (WHERE is_stockout) AS stockout_bins,
       COUNT(*) FILTER (WHERE is_below_reorder) AS below_reorder_bins,
       COUNT(*) FILTER (WHERE is_excess) AS excess_bins,
       COALESCE(SUM(excess_value_usd), 0) AS excess_usd
FROM v_inventory_health
"""

TOOLS_WITH_STOCKOUT_SQL = """
SELECT COUNT(*) FROM v_tool_parts_risk WHERE stocked_out_parts > 0
"""

COVERAGE_SQL = """
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE certified_techs >= target_techs)
             / NULLIF(COUNT(*), 0), 1) AS coverage_pct,
       COUNT(*) FILTER (WHERE is_single_point_of_failure) AS spof_cells
FROM v_training_coverage
"""

EXPIRING_SQL = """
SELECT COUNT(*) FILTER (WHERE tc.expires_date BETWEEN analytics_as_of()
                AND analytics_as_of() + INTERVAL '90 days') AS expiring,
       COUNT(*) AS active
FROM tech_certifications tc
JOIN technicians te ON te.tech_id = tc.tech_id
WHERE tc.status = 'active' AND te.is_active
"""

STALE_SQL = """
SELECT COUNT(*) FROM training_completions
WHERE completed_date IS NULL
  AND enrolled_date < analytics_as_of() - INTERVAL '120 days'
"""

MEDIAN_TTC_SQL = """
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY completed_date - enrolled_date)
FROM training_completions
WHERE completed_date IS NOT NULL
"""

COVERAGE_BY_SHIFT_SQL = """
SELECT shift,
       ROUND(AVG(coverage_ratio), 2) AS ratio,
       COUNT(*) FILTER (WHERE certified_techs = 0) AS uncovered,
       SUM(GREATEST(target_techs - certified_techs, 0)) AS techs_needed
FROM v_training_coverage
GROUP BY shift
ORDER BY shift
"""

COVERAGE_BY_TYPE_SQL = """
SELECT tool_type, ROUND(AVG(coverage_ratio), 2) AS ratio
FROM v_training_coverage
GROUP BY tool_type
ORDER BY ratio
LIMIT 2
"""

LONG_LEAD_SQL = """
SELECT COUNT(*) AS n_long_lead,
       COALESCE(SUM((ih.reorder_point + ih.safety_stock) * p.unit_cost), 0)
           AS replenish_cost
FROM v_inventory_health ih
JOIN parts p ON p.part_id = ih.part_id
WHERE ih.is_stockout AND p.lead_time_days >= 45
"""

TOOLS_WITH_LONGLEAD_SQL = """
SELECT COUNT(DISTINCT t.tool_id)
FROM tools t
JOIN tool_bom b ON b.tool_id = t.tool_id
JOIN parts p ON p.part_id = b.part_id
JOIN v_inventory_health ih ON ih.site_id = t.site_id AND ih.part_id = b.part_id
WHERE ih.is_stockout AND p.lead_time_days >= 45
"""

TOP10_SQL = """
SELECT s.site_code, r.tool_code, r.tool_type, r.criticality,
       r.readiness_score, r.risk_band, r.top_reason
FROM v_tool_readiness r
JOIN sites s ON s.site_id = r.site_id
ORDER BY r.readiness_score
LIMIT 10
"""


def _read_env_file() -> dict[str, str]:
    """Read KEY=VALUE pairs from the repo .env file (no python-dotenv dep)."""
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


def connect() -> Engine:
    """Build an engine for the fabtool database (env vars, .env fallback)."""
    file_env = _read_env_file()

    def val(key: str, default: str) -> str:
        return os.environ.get(key) or file_env.get(key) or default

    url = (f"postgresql+psycopg2://{val('FABTOOL_DB_USER', 'fabtool')}"
           f":{val('POSTGRES_PASSWORD', '')}"
           f"@{val('FABTOOL_DB_HOST', 'localhost')}"
           f":{val('FABTOOL_DB_PORT', '5433')}"
           f"/{val('FABTOOL_DB_NAME', 'fabtool')}")
    return create_engine(url)


def refresh_materialized_views(engine: Engine) -> None:
    """Refresh all materialized views in dependency order."""
    with engine.begin() as conn:
        for mv in MATVIEWS:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {mv}"))
    log.info("refreshed %d materialized views", len(MATVIEWS))


def run_script(relpath: str, args: list[str]) -> None:
    """Run another repo script with this interpreter; halt on non-zero exit."""
    proc = subprocess.run([sys.executable, str(ROOT / relpath), *args], cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"{relpath} exited with code {proc.returncode}")
    log.info("ran %s %s", relpath, " ".join(args))


def compute_findings_values(engine: Engine, as_of: dt.date) -> dict[str, str]:
    """Query every metric embedded in the FINDINGS template and format it."""
    def q(sql: str) -> pd.DataFrame:
        return pd.read_sql(text(sql), engine)

    risk = q(RISK_SQL).iloc[0]
    stock = q(STOCK_SQL).iloc[0]
    tools_with_stockout = int(q(TOOLS_WITH_STOCKOUT_SQL).iloc[0, 0])
    cov = q(COVERAGE_SQL).iloc[0]
    expiring = q(EXPIRING_SQL).iloc[0]
    stale = int(q(STALE_SQL).iloc[0, 0])
    median_ttc = q(MEDIAN_TTC_SQL).iloc[0, 0]
    by_shift = q(COVERAGE_BY_SHIFT_SQL).set_index("shift")
    by_type = q(COVERAGE_BY_TYPE_SQL)
    long_lead = q(LONG_LEAD_SQL).iloc[0]
    tools_longlead = int(q(TOOLS_WITH_LONGLEAD_SQL).iloc[0, 0])
    top10 = q(TOP10_SQL)

    total_tools = int(risk["total_tools"])
    critical = int(risk["critical_count"])
    at_risk = int(risk["at_risk_count"])
    flagged = critical + at_risk

    expiring_90d = int(expiring["expiring"])
    active_certs = int(expiring["active"])

    top10_rows = []
    for rank, row in enumerate(top10.itertuples(), start=1):
        top10_rows.append(
            f"| {rank} | {row.tool_code} | {row.site_code} | {row.tool_type} "
            f"| {row.criticality} | {float(row.readiness_score):.1f} "
            f"| {row.risk_band} | {row.top_reason} |")
    top10_table = "\n".join(top10_rows) if top10_rows else "| — | — |"

    thin1 = by_type.iloc[0] if len(by_type) > 0 else None
    thin2 = by_type.iloc[1] if len(by_type) > 1 else None

    return {
        "as_of_date": as_of.isoformat(),
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_tools": f"{total_tools:,}",
        "critical_count": f"{critical:,}",
        "at_risk_count": f"{at_risk:,}",
        "flagged_count": f"{flagged:,}",
        "flagged_pct": f"{100.0 * flagged / total_tools:.0f}%",
        "stockout_bins": f"{int(stock['stockout_bins']):,}",
        "total_bins": f"{int(stock['total_bins']):,}",
        "below_reorder_bins": f"{int(stock['below_reorder_bins']):,}",
        "tools_with_stockout": f"{tools_with_stockout:,}",
        "tools_with_stockout_pct": f"{100.0 * tools_with_stockout / total_tools:.0f}%",
        "excess_bins": f"{int(stock['excess_bins']):,}",
        "excess_usd": f"${float(stock['excess_usd']):,.0f}",
        "coverage_pct": f"{float(cov['coverage_pct']):.1f}%",
        "spof_cells": f"{int(cov['spof_cells']):,}",
        "expiring_90d": f"{expiring_90d:,}",
        "expiring_pct": f"{100.0 * expiring_90d / active_certs:.0f}%",
        "stale_trainings": f"{stale:,}",
        "shift_a_ratio": f"{float(by_shift.loc['A', 'ratio']):.2f}",
        "shift_d_ratio": f"{float(by_shift.loc['D', 'ratio']):.2f}",
        "d_uncovered_cells": f"{int(by_shift.loc['D', 'uncovered']):,}",
        "d_techs_needed": f"{int(by_shift.loc['D', 'techs_needed']):,}",
        "thin1_type": str(thin1["tool_type"]) if thin1 is not None else "—",
        "thin1_ratio": f"{float(thin1['ratio']):.2f}" if thin1 is not None else "—",
        "thin2_type": str(thin2["tool_type"]) if thin2 is not None else "—",
        "thin2_ratio": f"{float(thin2['ratio']):.2f}" if thin2 is not None else "—",
        "n_long_lead": f"{int(long_lead['n_long_lead']):,}",
        "replenish_cost": f"${float(long_lead['replenish_cost']):,.0f}",
        "tools_with_longlead": f"{tools_longlead:,}",
        "median_ttc": f"{float(median_ttc):.1f}",
        "top10_table": top10_table,
    }


def regenerate_findings(values: dict[str, str]) -> None:
    """Render docs/FINDINGS.md from its template using the computed values."""
    text = FINDINGS_TEMPLATE.read_text()
    placeholders = set(re.findall(r"\{\{(\w+)\}\}", text))
    unknown = placeholders - set(values)
    if unknown:
        raise SystemExit(
            f"FINDINGS template references unknown keys: {sorted(unknown)}")
    for key in placeholders:
        text = text.replace("{{" + key + "}}", values[key])
    FINDINGS_OUT.write_text(text)
    log.info("wrote %s (%d placeholders)", FINDINGS_OUT, len(placeholders))


def main() -> None:
    """Run the full pipeline: refresh -> check -> export -> findings."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    as_of = dt.date.today()
    engine = connect()
    refresh_materialized_views(engine)
    run_script("scripts/data_quality.py", [])
    run_script("scripts/export_reports.py", ["--site", "ALL", "--out", "exports"])
    values = compute_findings_values(engine, as_of)
    regenerate_findings(values)
    log.info("pipeline complete; findings as of %s", as_of)


if __name__ == "__main__":
    main()
