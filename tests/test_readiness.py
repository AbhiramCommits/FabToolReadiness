"""v_tool_readiness: score bounds, band thresholds, and the critical-tool
scenario (stocked-out long-lead part + zero certified techs).

Hand-computed fixture expectations (as-of 2026-01-15):

  T1 ETCH site1 crit 5: parts = 10*(1+5/90) + 10*(1+90/90) = 30.5556,
      training = 4 uncovered shifts * 20 = 80
      readiness = 100 - (0.55*30.6 + 0.45*80) * 1.4 = 26.0     -> critical
  T2 CMP  site1 crit 3: parts = 30.5556, training = 3*20 + 1*10 = 70
      readiness = 100 - (16.8056 + 31.5) * 1.2 = 42.0            -> at_risk
  T3 ETCH site2 crit 2: parts = 4*(1+90/90) = 8, training = 3*10 + 1*2 = 32
      readiness = 100 - (4.4 + 14.4) * 1.1 = 79.3                -> healthy
  T4 CMP  site2 crit 1: parts = 0, training = 2*20 + 2*10 + 2 = 62
      readiness = 100 - (0 + 27.9) * 1.0 = 72.1                  -> watch
"""

import pandas as pd
import pytest
from sqlalchemy import text

EXPECTED = {
    1: ("critical", 26.0),
    2: ("at_risk", 42.0),
    3: ("healthy", 79.3),
    4: ("watch", 72.1),
}


def load(engine) -> pd.DataFrame:
    return pd.read_sql(text("SELECT * FROM v_tool_readiness ORDER BY tool_id"),
                       engine)


def test_score_bounds(engine):
    df = load(engine)
    assert len(df) == 4
    assert df["readiness_score"].between(0, 100).all()
    assert df["parts_risk_score"].between(0, 100).all()
    assert df["training_risk_score"].between(0, 100).all()


def test_band_assignment_thresholds(engine):
    df = load(engine).set_index("tool_id")
    for tool_id, (band, score) in EXPECTED.items():
        assert df.loc[tool_id, "risk_band"] == band
        assert df.loc[tool_id, "readiness_score"] == pytest.approx(score,
                                                                   abs=0.1)
    # thresholds implied by the band column
    assert df.loc[1, "readiness_score"] < 30            # critical
    assert 30 <= df.loc[2, "readiness_score"] < 55      # at_risk
    assert 55 <= df.loc[4, "readiness_score"] < 75      # watch
    assert df.loc[3, "readiness_score"] >= 75           # healthy


def test_parts_risk_scores(engine):
    pr = pd.read_sql(text("SELECT * FROM v_tool_parts_risk ORDER BY tool_id"),
                     engine).set_index("tool_id")
    assert pr.loc[1, "parts_risk_score"] == pytest.approx(30.6, abs=0.1)
    assert pr.loc[2, "parts_risk_score"] == pytest.approx(30.6, abs=0.1)
    assert pr.loc[3, "parts_risk_score"] == pytest.approx(8.0, abs=0.1)
    assert pr.loc[4, "parts_risk_score"] == pytest.approx(0.0, abs=0.1)
    assert pr.loc[1, "stocked_out_parts"] == 2
    assert pr.loc[3, "below_reorder_parts"] == 1
    assert pr.loc[3, "min_days_of_supply"] == pytest.approx(90.09, abs=0.01)


def test_critical_tool_stocked_out_long_lead_and_no_certified_techs(engine):
    pr = pd.read_sql(text("SELECT * FROM v_tool_parts_risk WHERE tool_id = 1"),
                     engine).iloc[0]
    assert pr["stocked_out_parts"] == 2
    # part 2 (lead time 90 days) is on tool 1's BOM and stocked out
    long_lead = pd.read_sql(text("""
        SELECT ih.is_stockout
        FROM tool_bom b
        JOIN v_inventory_health ih
          ON ih.site_id = (SELECT site_id FROM tools WHERE tool_id = 1)
         AND ih.part_id = b.part_id
        JOIN parts p ON p.part_id = b.part_id
        WHERE b.tool_id = 1 AND p.lead_time_days = 90
    """), engine)
    assert len(long_lead) == 1 and bool(long_lead.iloc[0]["is_stockout"])

    # zero certified techs for ETCH at site 1
    cov = pd.read_sql(text("""
        SELECT SUM(certified_techs) AS techs
        FROM v_training_coverage
        WHERE tool_type = 'ETCH' AND site_id = 1
    """), engine).iloc[0]["techs"]
    assert cov == 0

    row = load(engine).set_index("tool_id").loc[1]
    assert row["risk_band"] == "critical"
    assert row["readiness_score"] == pytest.approx(26.0, abs=0.1)
    assert "shift" in row["top_reason"] or "parts" in row["top_reason"]


def test_top_reason_is_text(engine):
    df = load(engine)
    assert df["top_reason"].notna().all()
    assert df["top_reason"].str.startswith(
        ("parts:", "training:", "no material issues")).all()
