#!/usr/bin/env python3
"""Export analyst-facing deliverables for fabtoolreadiness.

Produces:
  * Flat Tableau-ready CSVs under <out>/tableau/, one per analytics view,
    denormalized with site/tool/part dimensions and a snapshot_date column.
  * A formatted Excel tracker <out>/FabToolReadiness_Tracker.xlsx
    (Summary with KPIs and charts, Reorder Tracker, Training Tracker,
    At-Risk Tools, Data Dictionary).

The --as-of flag controls the analytics snapshot date: the materialized views
are refreshed inside a transaction with fabtool.as_of set, read, and the
transaction is rolled back so the database is left unchanged.

Usage:
    python scripts/export_reports.py --site ALL --out exports/
"""

import argparse
import datetime as dt
import logging
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

log = logging.getLogger("export_reports")

MATVIEWS = ["v_inventory_health", "v_tool_parts_risk",
            "v_training_coverage", "v_tool_readiness"]

TABLEAU_CSVS = ["tool_readiness", "inventory_health", "parts_consumption",
                "training_coverage", "training_throughput"]

WORKBOOK = "FabToolReadiness_Tracker.xlsx"


# ---------------------------------------------------------------------------
# Database plumbing
# ---------------------------------------------------------------------------

def load_env() -> dict:
    env = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def connect():
    env = load_env()
    url = (f"postgresql+psycopg2://{env.get('FABTOOL_DB_USER', 'fabtool')}"
           f":{env.get('POSTGRES_PASSWORD', '')}"
           f"@{env.get('FABTOOL_DB_HOST', 'localhost')}"
           f":{env.get('FABTOOL_DB_PORT', '5433')}"
           f"/{env.get('FABTOOL_DB_NAME', 'fabtool')}")
    return create_engine(url)


# ---------------------------------------------------------------------------
# Data gathering (runs inside a rolled-back transaction with fabtool.as_of set)
# ---------------------------------------------------------------------------

def resolve_site(conn, site_arg):
    """Return site_id for --site (None = ALL), or exit with an error."""
    code = site_arg.strip().upper()
    if code == "ALL":
        return None
    if not re.fullmatch(r"[A-Z0-9_]{1,10}", code):
        log.error("invalid site code %r", site_arg)
        sys.exit(2)
    row = pd.read_sql(
        text(f"SELECT site_id, site_code FROM sites WHERE site_code = '{code}'"),
        conn)
    if row.empty:
        log.error("unknown site code %r (known: ALL or a site_code in sites)", site_arg)
        sys.exit(2)
    return int(row.iloc[0]["site_id"])


def where(al):
    return f"WHERE {al}.site_id = {SITE_ID}" if SITE_ID else ""


def and_where(al):
    return f"AND {al}.site_id = {SITE_ID}" if SITE_ID else ""


def gather(conn, as_of, site_id):
    global SITE_ID
    SITE_ID = site_id
    asof = as_of.isoformat()
    data = {}

    # -- Tableau CSVs --------------------------------------------------------
    data["tool_readiness"] = pd.read_sql(text(f"""
        SELECT DATE '{asof}' AS snapshot_date, s.site_code,
               r.tool_id, r.tool_code, r.tool_type, r.process_area,
               r.criticality, r.parts_risk_score, r.training_risk_score,
               r.readiness_score, r.risk_band, r.top_reason
        FROM v_tool_readiness r
        JOIN sites s ON s.site_id = r.site_id
        {where('r')}
        ORDER BY r.readiness_score
    """), conn)

    data["inventory_health"] = pd.read_sql(text(f"""
        SELECT DATE '{asof}' AS snapshot_date, s.site_code,
               i.part_id, i.part_number, p.description, p.lead_time_days,
               p.is_consumable, i.on_hand_qty, i.reorder_point, i.safety_stock,
               i.unit_cost, i.avg_daily_usage_90d, i.days_of_supply,
               i.last_consumption_date, i.consumption_qty_180d,
               i.last_counted_date, i.is_stockout, i.is_below_reorder,
               i.is_excess, i.excess_value_usd
        FROM v_inventory_health i
        JOIN parts p ON p.part_id = i.part_id
        JOIN sites s ON s.site_id = i.site_id
        {where('i')}
        ORDER BY s.site_code, i.part_number
    """), conn)

    data["parts_consumption"] = pd.read_sql(text(f"""
        SELECT DATE '{asof}' AS snapshot_date, s.site_code,
               c.part_id, p.part_number, p.description, p.is_consumable,
               c.month, c.consumption_qty, c.avg_daily_usage_90d,
               c.mom_change_qty, c.mom_change_pct
        FROM v_parts_consumption c
        JOIN parts p ON p.part_id = c.part_id
        JOIN sites s ON s.site_id = c.site_id
        {where('c')}
        ORDER BY s.site_code, p.part_number, c.month
    """), conn)

    data["training_coverage"] = pd.read_sql(text(f"""
        SELECT DATE '{asof}' AS snapshot_date, s.site_code,
               tc.tool_type, tc.shift, tc.certified_techs, tc.target_techs,
               tc.coverage_ratio, tc.certs_expiring_90d,
               tc.is_single_point_of_failure
        FROM v_training_coverage tc
        JOIN sites s ON s.site_id = tc.site_id
        {where('tc')}
        ORDER BY s.site_code, tc.tool_type, tc.shift
    """), conn)

    data["training_throughput"] = pd.read_sql(text(f"""
        SELECT DATE '{asof}' AS snapshot_date, s.site_code,
               tt.month, tt.enrolled_count, tt.completed_count,
               tt.completion_rate, tt.median_days_to_certify,
               tt.stale_in_progress_count
        FROM v_training_throughput tt
        JOIN sites s ON s.site_id = tt.site_id
        {where('tt')}
        ORDER BY s.site_code, tt.month
    """), conn)

    # -- Workbook inputs -----------------------------------------------------
    kpi_risk = pd.read_sql(text(f"""
        SELECT COUNT(*) AS total_tools,
               COUNT(*) FILTER (WHERE risk_band = 'critical') AS critical_tools,
               COUNT(*) FILTER (WHERE risk_band = 'at_risk') AS at_risk_tools
        FROM v_tool_readiness r {where('r')}
    """), conn)
    data["kpi_risk"] = kpi_risk.iloc[0]

    kpi_stock = pd.read_sql(text(f"""
        SELECT COUNT(*) FILTER (WHERE is_stockout) AS total_stockouts,
               COALESCE(SUM(excess_value_usd), 0) AS excess_usd
        FROM v_inventory_health i {where('i')}
    """), conn)
    data["kpi_stock"] = kpi_stock.iloc[0]

    kpi_coverage = pd.read_sql(text(f"""
        SELECT 100.0 * COUNT(*) FILTER (WHERE certified_techs >= target_techs)
                     / NULLIF(COUNT(*), 0) AS coverage_pct
        FROM v_training_coverage tc {where('tc')}
    """), conn)
    data["kpi_coverage"] = float(kpi_coverage.iloc[0]["coverage_pct"])

    kpi_ttc = pd.read_sql(text(f"""
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP
                 (ORDER BY tc.completed_date - tc.enrolled_date) AS median_ttc
        FROM training_completions tc
        JOIN technicians t ON t.tech_id = tc.tech_id
        WHERE tc.completed_date IS NOT NULL
          AND tc.completed_date <= DATE '{asof}'
          {and_where('t')}
    """), conn)
    data["kpi_median_ttc"] = kpi_ttc.iloc[0]["median_ttc"]

    data["risk_by_site"] = pd.read_sql(text(f"""
        SELECT s.site_code, COUNT(*) AS at_risk_tools
        FROM v_tool_readiness r
        JOIN sites s ON s.site_id = r.site_id
        WHERE r.risk_band IN ('critical', 'at_risk')
        {and_where('r')}
        GROUP BY s.site_code
        ORDER BY s.site_code
    """), conn)

    data["consumption_by_month"] = pd.read_sql(text(f"""
        SELECT c.month, SUM(c.consumption_qty) AS consumption_qty
        FROM v_parts_consumption c {where('c')}
        GROUP BY c.month
        ORDER BY c.month
    """), conn)

    data["reorder_tracker"] = pd.read_sql(text(f"""
        SELECT s.site_code, ih.part_number, p.description,
               ih.on_hand_qty, ih.reorder_point, ih.safety_stock,
               p.lead_time_days, p.unit_cost, ih.avg_daily_usage_90d,
               ih.days_of_supply,
               CASE WHEN ih.is_stockout THEN 'STOCKOUT'
                    ELSE 'BELOW REORDER' END AS status,
               (ih.reorder_point + ih.safety_stock - ih.on_hand_qty)
                   AS suggested_order_qty
        FROM v_inventory_health ih
        JOIN parts p ON p.part_id = ih.part_id
        JOIN sites s ON s.site_id = ih.site_id
        WHERE ih.is_stockout OR ih.is_below_reorder
        {and_where('ih')}
        ORDER BY ih.is_stockout DESC, p.lead_time_days DESC,
                 suggested_order_qty DESC
    """), conn)

    data["expiring_certs"] = pd.read_sql(text(f"""
        SELECT s.site_code, te.shift, te.employee_code AS owner,
               c.tool_type, c.cert_code, c.cert_name,
               tc.expires_date,
               (tc.expires_date - DATE '{asof}') AS days_to_expiry
        FROM tech_certifications tc
        JOIN technicians te ON te.tech_id = tc.tech_id
        JOIN certifications c ON c.cert_id = tc.cert_id
        JOIN sites s ON s.site_id = te.site_id
        WHERE tc.status = 'active'
          AND tc.expires_date BETWEEN DATE '{asof}'
                                  AND DATE '{asof}' + INTERVAL '90 days'
        {and_where('te')}
        ORDER BY tc.expires_date, s.site_code
    """), conn)

    data["spof_gaps"] = pd.read_sql(text(f"""
        SELECT s.site_code, tc.tool_type, tc.shift,
               tc.certified_techs, tc.target_techs,
               own.employee_code AS owner, tc.certs_expiring_90d
        FROM v_training_coverage tc
        JOIN sites s ON s.site_id = tc.site_id
        LEFT JOIN LATERAL (
            SELECT te.employee_code
            FROM tech_certifications tcc
            JOIN technicians te ON te.tech_id = tcc.tech_id
            JOIN certifications c ON c.cert_id = tcc.cert_id
            WHERE te.is_active AND tcc.status = 'active'
              AND te.site_id = tc.site_id
              AND c.tool_type = tc.tool_type
              AND te.shift = tc.shift
            LIMIT 1
        ) own ON true
        WHERE tc.is_single_point_of_failure
        {and_where('tc')}
        ORDER BY s.site_code, tc.tool_type, tc.shift
    """), conn)

    data["at_risk_tools"] = pd.read_sql(text(f"""
        SELECT s.site_code, r.tool_code, r.tool_type, r.process_area,
               r.criticality, r.parts_risk_score, r.training_risk_score,
               r.readiness_score, r.risk_band, r.top_reason
        FROM v_tool_readiness r
        JOIN sites s ON s.site_id = r.site_id
        WHERE r.risk_band IN ('critical', 'at_risk')
        {and_where('r')}
        ORDER BY r.readiness_score
    """), conn)

    return data


# ---------------------------------------------------------------------------
# Tableau CSVs
# ---------------------------------------------------------------------------

def write_csvs(out_dir, data):
    tableau_dir = out_dir / "tableau"
    tableau_dir.mkdir(parents=True, exist_ok=True)
    for name in TABLEAU_CSVS:
        path = tableau_dir / f"{name}.csv"
        data[name].to_csv(path, index=False)
        log.info("wrote %s (%d rows)", path, len(data[name]))


# ---------------------------------------------------------------------------
# Excel workbook
# ---------------------------------------------------------------------------

def write_workbook(out_dir, data, as_of, scope_label):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / WORKBOOK
    sheet_rows = {}

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        wb = writer.book

        fmt = {name: wb.add_format({"num_format": code}) for name, code in {
            "int": "#,##0",
            "num1": "0.0",
            "num2": "0.00",
            "num3": "0.000",
            "money": "$#,##0",
            "money2": "$#,##0.00",
            "pct": "0.0%",
            "date": "yyyy-mm-dd",
        }.items()}
        title_fmt = wb.add_format({"bold": True, "font_size": 14})
        bold = wb.add_format({"bold": True})
        header_fmt = wb.add_format({"bold": True, "bg_color": "#D9E1F2",
                                    "border": 1, "text_wrap": True})
        cf_red = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        cf_amber = wb.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})
        cf_green = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})

        # ---- Summary -------------------------------------------------------
        kpi = data["kpi_risk"]
        ws = wb.add_worksheet("Summary")
        ws.write("A1", "Fab Tool Readiness Tracker", title_fmt)
        ws.write("A2", "Snapshot date", bold)
        ws.write_datetime("B2", dt.datetime.combine(as_of, dt.time()), fmt["date"])
        ws.write("A3", "Scope", bold)
        ws.write("B3", scope_label)

        kpi_rows = [
            ("Tools at critical / at-risk",
             int(kpi["critical_tools"]) + int(kpi["at_risk_tools"]), "int"),
            ("  of which critical", int(kpi["critical_tools"]), "int"),
            ("  of which at_risk", int(kpi["at_risk_tools"]), "int"),
            ("Total stockouts (part/site)", int(data["kpi_stock"]["total_stockouts"]), "int"),
            ("Excess inventory value", float(data["kpi_stock"]["excess_usd"]), "money"),
            ("Overall cert coverage (vs 2/shift)",
             data["kpi_coverage"] / 100.0, "pct"),
            ("Median time-to-certify (days)",
             float(data["kpi_median_ttc"] or 0.0), "num1"),
        ]
        row = 5
        for label, value, f in kpi_rows:
            ws.write(row, 0, label)
            ws.write_number(row, 1, value, fmt[f])
            row += 1
        sheet_rows["Summary"] = f"{row} KPI + chart data rows"

        # bar chart data + chart
        bar = data["risk_by_site"].rename(
            columns={"site_code": "Site", "at_risk_tools": "At-risk tools"})
        bar_hdr = 4
        for c, col in enumerate(bar.columns):
            ws.write(bar_hdr, 4 + c, col, header_fmt)
        bar.to_excel(writer, sheet_name="Summary", startrow=bar_hdr + 1,
                     startcol=4, header=False, index=False)
        bar_last = bar_hdr + len(bar)
        chart_bar = wb.add_chart({"type": "column"})
        chart_bar.add_series({
            "name": "At-risk tools",
            "categories": ["Summary", bar_hdr + 1, 4, bar_last, 4],
            "values": ["Summary", bar_hdr + 1, 5, bar_last, 5],
        })
        chart_bar.set_title({"name": "At-risk tools by site"})
        chart_bar.set_legend({"none": True})
        ws.insert_chart("H4", chart_bar)

        # line chart data + chart
        line = data["consumption_by_month"].copy()
        line["Month"] = pd.to_datetime(line["month"]).dt.strftime("%Y-%m")
        line = line[["Month", "consumption_qty"]].rename(
            columns={"consumption_qty": "Units consumed"})
        line_hdr = bar_last + 3
        for c, col in enumerate(line.columns):
            ws.write(line_hdr, 4 + c, col, header_fmt)
        line.to_excel(writer, sheet_name="Summary", startrow=line_hdr + 1,
                      startcol=4, header=False, index=False)
        line_last = line_hdr + len(line)
        chart_line = wb.add_chart({"type": "line"})
        chart_line.add_series({
            "name": "Monthly consumption",
            "categories": ["Summary", line_hdr + 1, 4, line_last, 4],
            "values": ["Summary", line_hdr + 1, 5, line_last, 5],
        })
        chart_line.set_title({"name": "Monthly consumption (units)"})
        chart_line.set_legend({"none": True})
        ws.insert_chart("H25", chart_line)

        ws.set_column("A:A", 34)
        ws.set_column("B:B", 14)
        ws.set_column("E:E", 12)
        ws.set_column("F:F", 16)

        # ---- shared table writer ------------------------------------------
        def write_table(name, df, col_specs, conditional=None,
                        autofilter=True, freeze=True, startrow=0, title=None):
            ws = wb.add_worksheet(name)
            r = startrow
            if title:
                ws.write(r, 0, title, title_fmt)
                r += 1
            header_row = r
            for c, col in enumerate(df.columns):
                ws.write(header_row, c, col, header_fmt)
            df.to_excel(writer, sheet_name=name, startrow=header_row + 1,
                        header=False, index=False)
            last = header_row + len(df)
            for c, (width, f) in enumerate(col_specs):
                ws.set_column(c, c, width, f)
            if autofilter and len(df):
                ws.autofilter(header_row, 0, last, len(df.columns) - 1)
            if freeze:
                ws.freeze_panes(header_row + 1, 0)
            if conditional and len(df):
                for first_col, last_col, spec in conditional:
                    ws.conditional_format(header_row + 1, first_col,
                                          last, last_col, spec)
            sheet_rows[name] = len(df)
            return ws

        # ---- Reorder Tracker ------------------------------------------------
        reorder = data["reorder_tracker"]
        reorder_specs = [
            (10, None), (12, None), (42, None),
            (10, fmt["int"]), (10, fmt["int"]), (10, fmt["int"]),
            (10, fmt["int"]), (12, fmt["money2"]), (12, fmt["num3"]),
            (11, fmt["num1"]), (14, None), (13, fmt["int"]),
        ]
        write_table("Reorder Tracker", reorder, reorder_specs, conditional=[
            (10, 10, {"type": "text", "criteria": "containing",
                      "value": "STOCKOUT", "format": cf_red}),
            (10, 10, {"type": "text", "criteria": "containing",
                      "value": "BELOW REORDER", "format": cf_amber}),
        ])

        # ---- Training Tracker ----------------------------------------------
        ws_tr = wb.add_worksheet("Training Tracker")
        exp = data["expiring_certs"]
        r = 0
        ws_tr.write(r, 0, "Expiring certifications (next 90 days)", title_fmt)
        r += 1
        exp_hdr = r
        for c, col in enumerate(exp.columns):
            ws_tr.write(exp_hdr, c, col, header_fmt)
        exp.to_excel(writer, sheet_name="Training Tracker",
                     startrow=exp_hdr + 1, header=False, index=False)
        exp_last = exp_hdr + len(exp)
        exp_specs = [(10, None), (7, None), (12, None), (10, None),
                     (10, None), (36, None), (12, fmt["date"]), (12, fmt["int"])]
        for c, (width, f) in enumerate(exp_specs):
            ws_tr.set_column(c, c, width, f)
        if len(exp):
            ws_tr.conditional_format(exp_hdr + 1, 7, exp_last, 7,
                {"type": "cell", "criteria": "<=", "value": 30, "format": cf_red})
            ws_tr.conditional_format(exp_hdr + 1, 7, exp_last, 7,
                {"type": "cell", "criteria": "between", "minimum": 31,
                 "maximum": 60, "format": cf_amber})
            ws_tr.conditional_format(exp_hdr + 1, 7, exp_last, 7,
                {"type": "cell", "criteria": ">", "value": 60, "format": cf_green})
        n_exp = len(exp)

        spof = data["spof_gaps"]
        r = exp_last + 2
        ws_tr.write(r, 0, "Single-point-of-failure coverage gaps", title_fmt)
        r += 1
        spof_hdr = r
        for c, col in enumerate(spof.columns):
            ws_tr.write(spof_hdr, c, col, header_fmt)
        spof.to_excel(writer, sheet_name="Training Tracker",
                      startrow=spof_hdr + 1, header=False, index=False)
        spof_specs = [(10, None), (10, None), (7, None), (12, fmt["int"]),
                      (12, fmt["int"]), (12, None), (14, fmt["int"])]
        for c, (width, f) in enumerate(spof_specs):
            ws_tr.set_column(c, c, width, f)
        ws_tr.freeze_panes(1, 0)
        sheet_rows["Training Tracker"] = f"{n_exp} expiring / {len(spof)} SPOF"

        # ---- At-Risk Tools ---------------------------------------------------
        at_risk = data["at_risk_tools"]
        at_risk_specs = [
            (10, None), (14, None), (10, None), (16, None), (10, fmt["int"]),
            (12, fmt["num1"]), (12, fmt["num1"]), (12, fmt["num1"]),
            (10, None), (46, None),
        ]
        write_table("At-Risk Tools", at_risk, at_risk_specs, conditional=[
            (8, 8, {"type": "text", "criteria": "containing",
                    "value": "critical", "format": cf_red}),
            (8, 8, {"type": "text", "criteria": "containing",
                    "value": "at_risk", "format": cf_amber}),
        ])

        # ---- Data Dictionary --------------------------------------------------
        dictionary = pd.DataFrame(DATA_DICTIONARY,
                                  columns=["Sheet", "Column", "Type",
                                           "Definition", "Source"])
        ws_dd = wb.add_worksheet("Data Dictionary")
        for c, col in enumerate(dictionary.columns):
            ws_dd.write(0, c, col, header_fmt)
        dictionary.to_excel(writer, sheet_name="Data Dictionary",
                            startrow=1, header=False, index=False)
        for c, width in enumerate([20, 30, 12, 78, 30]):
            ws_dd.set_column(c, c, width,
                             wb.add_format({"text_wrap": True}) if c == 3 else None)
        ws_dd.freeze_panes(1, 0)
        sheet_rows["Data Dictionary"] = len(dictionary)

    log.info("wrote %s (%s)", path,
             ", ".join(f"{k}: {v}" for k, v in sheet_rows.items()))


# ---------------------------------------------------------------------------
# Data dictionary content
# ---------------------------------------------------------------------------

DATA_DICTIONARY = [
    # Summary
    ("Summary", "Tools at critical / at-risk", "count",
     "Number of tools with readiness band 'critical' or 'at_risk'",
     "v_tool_readiness"),
    ("Summary", "Tools at critical", "count",
     "Number of tools with readiness band 'critical'", "v_tool_readiness"),
    ("Summary", "Tools at at_risk", "count",
     "Number of tools with readiness band 'at_risk'", "v_tool_readiness"),
    ("Summary", "Total stockouts (part/site)", "count",
     "Inventory rows with on_hand_qty = 0", "v_inventory_health"),
    ("Summary", "Excess inventory value", "USD",
     "Value of excess/obsolete stock (days_of_supply > 365 or no usage in 180 days)",
     "v_inventory_health"),
    ("Summary", "Overall cert coverage (vs 2/shift)", "percent",
     "Share of tool_type/site/shift cells with at least 2 certified techs",
     "v_training_coverage"),
    ("Summary", "Median time-to-certify (days)", "days",
     "Median days from enrollment to completion across completed trainings",
     "training_completions"),
    # Reorder Tracker
    ("Reorder Tracker", "site_code", "text", "Site where the part is stocked", "sites"),
    ("Reorder Tracker", "part_number", "text", "Part number", "parts"),
    ("Reorder Tracker", "description", "text", "Part description", "parts"),
    ("Reorder Tracker", "on_hand_qty", "int",
     "Current on-hand units (0 = stockout)", "inventory"),
    ("Reorder Tracker", "reorder_point", "int",
     "Policy reorder point", "inventory"),
    ("Reorder Tracker", "safety_stock", "int",
     "Policy safety stock", "inventory"),
    ("Reorder Tracker", "lead_time_days", "int",
     "Supplier lead time in days", "parts"),
    ("Reorder Tracker", "unit_cost", "USD",
     "Part unit cost", "parts"),
    ("Reorder Tracker", "avg_daily_usage_90d", "units/day",
     "Trailing-90-day average daily usage", "v_parts_consumption"),
    ("Reorder Tracker", "days_of_supply", "days",
     "on_hand_qty / avg_daily_usage_90d", "v_inventory_health"),
    ("Reorder Tracker", "status", "text",
     "STOCKOUT (on_hand = 0) or BELOW REORDER", "v_inventory_health"),
    ("Reorder Tracker", "suggested_order_qty", "int",
     "reorder_point + safety_stock - on_hand_qty", "v_inventory_health"),
    # Training Tracker
    ("Training Tracker", "Expiring: site_code / shift / owner", "text",
     "Site, shift and employee_code of the cert holder", "technicians"),
    ("Training Tracker", "Expiring: tool_type / cert_code / cert_name", "text",
     "Certification identifying the tool family and course", "certifications"),
    ("Training Tracker", "Expiring: expires_date", "date",
     "Certification expiry date (within 90 days of snapshot)", "tech_certifications"),
    ("Training Tracker", "Expiring: days_to_expiry", "days",
     "expires_date - snapshot date", "tech_certifications"),
    ("Training Tracker", "SPOF: tool_type / shift", "text",
     "Coverage cell with exactly one certified tech", "v_training_coverage"),
    ("Training Tracker", "SPOF: certified_techs / target_techs", "count",
     "Certified techs in the cell vs target of 2", "v_training_coverage"),
    ("Training Tracker", "SPOF: owner", "text",
     "Employee code of the single certified tech", "technicians"),
    ("Training Tracker", "SPOF: certs_expiring_90d", "count",
     "Certs in the cell expiring within 90 days", "v_training_coverage"),
    # At-Risk Tools
    ("At-Risk Tools", "site_code", "text", "Site of the tool", "sites"),
    ("At-Risk Tools", "tool_code", "text", "Tool identifier", "tools"),
    ("At-Risk Tools", "tool_type", "text", "Tool family", "tools"),
    ("At-Risk Tools", "process_area", "text", "Fab process area", "tools"),
    ("At-Risk Tools", "criticality", "int",
     "Tool criticality 1-5", "tools"),
    ("At-Risk Tools", "parts_risk_score", "score 0-100",
     "Parts risk from BOM stockouts/below-reorder", "v_tool_parts_risk"),
    ("At-Risk Tools", "training_risk_score", "score 0-100",
     "Training risk from coverage gaps", "v_training_coverage"),
    ("At-Risk Tools", "readiness_score", "score 0-100",
     "100 - criticality-weighted blend of the two risk scores", "v_tool_readiness"),
    ("At-Risk Tools", "risk_band", "text",
     "critical / at_risk / watch / healthy", "v_tool_readiness"),
    ("At-Risk Tools", "top_reason", "text",
     "Dominant risk driver as text", "v_tool_readiness"),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export Tableau CSVs and the Excel tracker.")
    parser.add_argument("--site", default="ALL",
                        help="Site filter: ALL or a site code (default: ALL)")
    parser.add_argument("--as-of", default=str(dt.date.today()),
                        help="Snapshot date YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default="exports",
                        help="Output directory (default: exports)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        as_of = dt.date.fromisoformat(args.as_of)
    except ValueError:
        log.error("invalid --as-of date %r (expected YYYY-MM-DD)", args.as_of)
        sys.exit(2)
    if as_of > dt.date.today():
        log.warning("--as-of %s is in the future", as_of)

    engine = connect()
    conn = engine.connect()
    tx = conn.begin()
    try:
        conn.execute(text("SET fabtool.as_of = :d"), {"d": as_of.isoformat()})
        for mv in MATVIEWS:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {mv}"))
        site_id = resolve_site(conn, args.site)
        log.info("gathering data as of %s (scope: %s)", as_of,
                 args.site.upper() if site_id else "ALL")
        data = gather(conn, as_of, site_id)
        tx.rollback()
    except Exception:
        tx.rollback()
        log.exception("export failed; no files were written")
        sys.exit(1)
    finally:
        conn.close()

    out_dir = Path(args.out)
    write_csvs(out_dir, data)
    scope_label = args.site.upper() if site_id else "ALL sites"
    write_workbook(out_dir, data, as_of, scope_label)
    log.info("export complete -> %s", out_dir.resolve())


if __name__ == "__main__":
    main()
