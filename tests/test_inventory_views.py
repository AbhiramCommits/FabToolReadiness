"""v_inventory_health: hand-computed expectations on the fixture.

All values are derived in tests/fixture_seed.sql's header comment; the
trailing-90-day usage is rounded to 4dp by v_parts_consumption, so
days_of_supply values carry that rounding (e.g. 20 / 0.0222 = 900.90).
"""

import pandas as pd
import pytest
from sqlalchemy import text

EXPECTED = {
    (1, 1): dict(is_stockout=True, is_below_reorder=False, is_excess=False,
                 days_of_supply=0.0, excess_value_usd=0.0, usage_90d=0.1),
    (1, 2): dict(is_stockout=True, is_below_reorder=False, is_excess=False,
                 days_of_supply=0.0, excess_value_usd=0.0, usage_90d=0.0111),
    (1, 3): dict(is_stockout=False, is_below_reorder=False, is_excess=True,
                 days_of_supply=900.90, excess_value_usd=1000.00,
                 usage_90d=0.0222),
    (2, 2): dict(is_stockout=False, is_below_reorder=True, is_excess=False,
                 days_of_supply=90.09, excess_value_usd=0.0, usage_90d=0.0111),
    (2, 4): dict(is_stockout=False, is_below_reorder=False, is_excess=True,
                 days_of_supply=2702.70, excess_value_usd=30.00,
                 usage_90d=0.0111),
}


def load(engine) -> pd.DataFrame:
    return pd.read_sql(
        text("SELECT * FROM v_inventory_health ORDER BY site_id, part_id"),
        engine)


def test_row_count(engine):
    assert len(load(engine)) == 5


def test_days_of_supply_matches_hand_computation(engine):
    df = load(engine)
    for (site_id, part_id), exp in EXPECTED.items():
        row = df[(df["site_id"] == site_id) & (df["part_id"] == part_id)].iloc[0]
        assert row["days_of_supply"] == pytest.approx(exp["days_of_supply"],
                                                      abs=0.01)


def test_flags_match_fixture(engine):
    df = load(engine)
    for (site_id, part_id), exp in EXPECTED.items():
        row = df[(df["site_id"] == site_id) & (df["part_id"] == part_id)].iloc[0]
        assert bool(row["is_stockout"]) is exp["is_stockout"]
        assert bool(row["is_below_reorder"]) is exp["is_below_reorder"]
        assert bool(row["is_excess"]) is exp["is_excess"]


def test_excess_value_is_on_hand_times_unit_cost(engine):
    df = load(engine)
    for (site_id, part_id), exp in EXPECTED.items():
        row = df[(df["site_id"] == site_id) & (df["part_id"] == part_id)].iloc[0]
        assert float(row["excess_value_usd"]) == pytest.approx(
            exp["excess_value_usd"], abs=0.01)


def test_usage_and_180d_history(engine):
    df = load(engine)
    # (site1, PART-003): last consumption is 2025-05-01, > 180 days before
    # the as-of date of 2026-01-15 -> zero 180-day usage, no recent date.
    row = df[(df["site_id"] == 1) & (df["part_id"] == 3)].iloc[0]
    assert row["consumption_qty_180d"] == 0
    assert pd.isna(row["last_consumption_date"])
    # (site1, PART-001): 9 units consumed inside the window.
    row = df[(df["site_id"] == 1) & (df["part_id"] == 1)].iloc[0]
    assert row["consumption_qty_180d"] == 9
    assert str(row["last_consumption_date"]) == "2026-01-05"


def test_reorder_policy_columns_passthrough(engine):
    df = load(engine)
    row = df[(df["site_id"] == 2) & (df["part_id"] == 2)].iloc[0]
    assert row["on_hand_qty"] == 1
    assert row["reorder_point"] == 3
    assert row["safety_stock"] == 2
