"""v_training_coverage: ratios, SPOF detection, and the 90-day expiry
boundary (exactly 90 days counts, 91 days does not)."""

import pandas as pd
import pytest
from sqlalchemy import text


def load(engine) -> pd.DataFrame:
    return pd.read_sql(text("SELECT * FROM v_training_coverage"), engine)


def cell(df, site_id, tool_type, shift) -> pd.Series:
    rows = df[(df["site_id"] == site_id)
              & (df["tool_type"] == tool_type)
              & (df["shift"] == shift)]
    assert len(rows) == 1, f"missing coverage cell {site_id}/{tool_type}/{shift}"
    return rows.iloc[0]


def test_grid_is_complete(engine):
    # 3 fixture tool types x 2 sites x 4 shifts
    assert len(load(engine)) == 24


def test_coverage_ratio(engine):
    df = load(engine)
    # two certified techs of target two
    assert cell(df, 2, "ETCH", "A")["certified_techs"] == 2
    assert cell(df, 2, "ETCH", "A")["coverage_ratio"] == pytest.approx(1.0)
    # one certified tech
    assert cell(df, 1, "CMP", "A")["certified_techs"] == 1
    assert cell(df, 1, "CMP", "A")["coverage_ratio"] == pytest.approx(0.5)
    # none: expired and inactive techs are excluded
    assert cell(df, 1, "ETCH", "B")["certified_techs"] == 0
    assert cell(df, 1, "ETCH", "A")["certified_techs"] == 0


def test_single_point_of_failure(engine):
    df = load(engine)
    assert bool(cell(df, 1, "CMP", "A")["is_single_point_of_failure"]) is True
    assert bool(cell(df, 2, "ETCH", "A")["is_single_point_of_failure"]) is False
    # exactly one tech for ETCH site2 shift B
    assert cell(df, 2, "ETCH", "B")["certified_techs"] == 1
    assert bool(cell(df, 2, "ETCH", "B")["is_single_point_of_failure"]) is True


def test_expiring_90d_boundary(engine):
    df = load(engine)
    # WETS site1 A holds two certs: one expiring exactly 90 days after the
    # as-of date (2026-04-15, counted) and one at 91 days (2026-04-16, not).
    assert cell(df, 1, "WETS", "A")["certified_techs"] == 2
    assert cell(df, 1, "WETS", "A")["certs_expiring_90d"] == 1
    # CMP site2: B-shift cert expires at exactly 90 days (counted), the
    # D-shift cert at 91 days (not counted) -> one expiring cert in total.
    total = df[(df["site_id"] == 2) & (df["tool_type"] == "CMP")][
        "certs_expiring_90d"].sum()
    assert total == 1


def test_expired_and_in_progress_certs_do_not_count(engine):
    df = load(engine)
    # ETCH site1: tech 2's cert is expired, tech 5 is inactive -> no
    # certified techs anywhere, and no expiring certs.
    et = df[(df["site_id"] == 1) & (df["tool_type"] == "ETCH")]
    assert et["certified_techs"].sum() == 0
    assert et["certs_expiring_90d"].sum() == 0
    # CMP site2 A: tech 3's cert is in_progress -> cell uncovered.
    assert cell(df, 2, "CMP", "A")["certified_techs"] == 0
