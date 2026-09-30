"""Schema constraints: CHECK / FK / PK rules actually reject bad rows."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def assert_rejected(engine, sql, *args):
    with pytest.raises(IntegrityError):
        with engine.connect() as conn:
            conn.execute(text(sql), *args)


def test_negative_on_hand_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO inventory (site_id, part_id, on_hand_qty, reorder_point,
                               safety_stock, last_counted_date)
        VALUES (1, 1, -1, 5, 2, '2026-01-01')
    """)


def test_invalid_movement_type_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO stock_movements (site_id, part_id, tool_id, movement_date,
                                     qty_delta, movement_type)
        VALUES (1, 1, 1, '2026-01-01', -1, 'transfer')
    """)


def test_zero_qty_delta_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO stock_movements (site_id, part_id, tool_id, movement_date,
                                     qty_delta, movement_type)
        VALUES (1, 1, 1, '2026-01-01', 0, 'adjustment')
    """)


def test_missing_tool_fk_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO tool_bom (tool_id, part_id, qty_per_tool)
        VALUES (999, 1, 1.0)
    """)


def test_cert_expiry_before_earned_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO tech_certifications (tech_id, cert_id, earned_date,
                                         expires_date, status)
        VALUES (9, 1, '2026-01-01', '2025-01-01', 'active')
    """)


def test_criticality_out_of_range_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO tools (site_id, tool_code, tool_type, process_area,
                           install_date, criticality)
        VALUES (1, 'T-999', 'ETCH', 'Dry Etch Bay', '2020-01-01', 6)
    """)


def test_invalid_shift_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO technicians (site_id, employee_code, hire_date, shift,
                                 is_active)
        VALUES (1, 'FAB-Z9999', '2020-01-01', 'E', TRUE)
    """)


def test_duplicate_bom_pk_rejected(engine):
    assert_rejected(engine, """
        INSERT INTO tool_bom (tool_id, part_id, qty_per_tool)
        VALUES (1, 1, 2.0)
    """)
