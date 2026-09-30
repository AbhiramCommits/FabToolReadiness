-- ===========================================================================
-- Deterministic fixture seed for the pytest suite and CI data-quality checks.
--
-- Small, hand-computable dataset anchored to an "as of" date of 2026-01-15
-- (set via the fabtool.as_of GUC by the test harness). Every aggregate the
-- analytics views compute over this fixture has a hand-derived expectation:
--
--   * (site 1, PART-001): 0 on hand, 9 units consumed in the last 90 days
--     -> avg daily usage 0.1, days of supply 0, stockout.
--   * (site 1, PART-002): 0 on hand, 1 unit consumed in the last 90 days,
--     90-day lead time -> stockout of a long-lead part.
--   * (site 1, PART-003): 20 on hand, no usage in the last 180 days
--     -> excess, value 20 * 50.00 = 1000.00.
--   * (site 2, PART-002): 1 on hand vs reorder point 3 -> below reorder,
--     days of supply 1 / (1/90) = 90.09.
--   * (site 2, PART-004): 30 on hand, 1 unit consumed in 90 days
--     -> days of supply 30 / (1/90) = 2702.70 -> excess, value 30.00.
--
-- Coverage: ETCH site 1 has zero certified techs on every shift; CMP site 1
-- shift A has one (SPOF); ETCH site 2 shift A has two; expiring-cert
-- boundaries use WETS-100: one cert expires exactly 90 days out, one at 91.
-- ===========================================================================

INSERT INTO sites (site_id, site_code, site_name, region) VALUES
    (1, 'TST',  'Test Site',   'Americas'),
    (2, 'TST2', 'Test Site 2', 'Europe');

INSERT INTO parts (part_id, part_number, description, unit_cost, lead_time_days, is_consumable) VALUES
    (1, 'PART-001', 'Fast consumable', 10.00,  5,  TRUE),
    (2, 'PART-002', 'Long-lead spare', 100.00, 90, FALSE),
    (3, 'PART-003', 'Obsolete spare',  50.00,  30, FALSE),
    (4, 'PART-004', 'Slow spare',      1.00,   7,  FALSE);

INSERT INTO tools (tool_id, site_id, tool_code, tool_type, process_area, install_date, criticality) VALUES
    (1, 1, 'ETCH-TST-001',  'ETCH', 'Dry Etch Bay',  '2020-01-01', 5),
    (2, 1, 'CMP-TST-001',   'CMP',  'Planarization', '2021-06-01', 3),
    (3, 2, 'ETCH-TST2-001', 'ETCH', 'Dry Etch Bay',  '2019-03-15', 2),
    (4, 2, 'CMP-TST2-001',  'CMP',  'Planarization', '2022-02-20', 1);

INSERT INTO tool_bom (tool_id, part_id, qty_per_tool) VALUES
    (1, 1, 2.0), (1, 2, 1.0),
    (2, 1, 4.0), (2, 2, 1.0), (2, 3, 1.0),
    (3, 2, 1.0), (3, 4, 1.0),
    (4, 4, 1.0);

INSERT INTO inventory (site_id, part_id, on_hand_qty, reorder_point, safety_stock, last_counted_date) VALUES
    (1, 1, 0,  5, 2, '2026-01-10'),
    (1, 2, 0,  3, 2, '2026-01-10'),
    (1, 3, 20, 2, 1, '2026-01-10'),
    (2, 2, 1,  3, 2, '2026-01-10'),
    (2, 4, 30, 4, 2, '2026-01-10');

INSERT INTO stock_movements (movement_id, site_id, part_id, tool_id, movement_date, qty_delta, movement_type) VALUES
    (1, 1, 1, 1, '2025-11-01', -3, 'consumption'),
    (2, 1, 1, 1, '2025-12-01', -3, 'consumption'),
    (3, 1, 1, 1, '2026-01-05', -3, 'consumption'),
    (4, 1, 2, 1, '2025-12-10', -1, 'consumption'),
    (5, 1, 3, 2, '2025-05-01', -2, 'consumption'),
    (6, 2, 2, 3, '2025-12-10', -1, 'consumption'),
    (7, 2, 4, 3, '2026-01-02', -1, 'consumption'),
    (8, 1, 1, 1, '2025-10-20', 10, 'receipt');

INSERT INTO technicians (tech_id, site_id, employee_code, hire_date, shift, is_active) VALUES
    (1,  1, 'FAB-A0001', '2020-01-05', 'A', TRUE),
    (2,  1, 'FAB-A0002', '2019-06-01', 'B', TRUE),
    (3,  2, 'FAB-A0003', '2021-02-10', 'A', TRUE),
    (4,  2, 'FAB-A0004', '2022-08-15', 'A', TRUE),
    (5,  1, 'FAB-A0005', '2018-03-20', 'A', FALSE),
    (6,  2, 'FAB-A0006', '2021-11-01', 'B', TRUE),
    (7,  2, 'FAB-A0007', '2022-05-05', 'C', TRUE),
    (8,  2, 'FAB-A0008', '2023-01-12', 'D', TRUE),
    (9,  1, 'FAB-A0009', '2020-09-09', 'A', TRUE),
    (10, 1, 'FAB-A0010', '2021-04-04', 'A', TRUE);

INSERT INTO certifications (cert_id, cert_code, cert_name, tool_type, validity_months) VALUES
    (1, 'ETCH-100', 'Etch certification', 'ETCH', 12),
    (2, 'CMP-100',  'CMP certification',  'CMP',  24),
    (3, 'WETS-100', 'Wets certification', 'WETS', 12);

INSERT INTO tech_certifications (tech_id, cert_id, earned_date, expires_date, status) VALUES
    (1,  2, '2024-06-01', '2026-06-01', 'active'),      -- CMP site1 A (expires 137d out)
    (2,  1, '2025-01-01', '2026-01-01', 'expired'),     -- ETCH site1 B (expired: excluded)
    (3,  1, '2025-04-20', '2026-04-20', 'active'),      -- ETCH site2 A (expires 95d out)
    (3,  2, NULL,         NULL,         'in_progress'), -- CMP site2 A (not active)
    (4,  1, '2025-03-10', '2026-03-10', 'active'),      -- ETCH site2 A (54d -> expiring)
    (5,  1, '2025-05-01', '2026-05-01', 'active'),      -- ETCH site1 A (tech inactive)
    (6,  1, '2026-01-10', '2027-01-10', 'active'),      -- ETCH site2 B
    (6,  2, '2024-04-15', '2026-04-15', 'active'),      -- CMP site2 B (exactly 90d -> expiring)
    (7,  1, '2025-06-01', '2026-06-01', 'active'),      -- ETCH site2 C
    (8,  1, '2025-06-15', '2026-06-15', 'active'),      -- ETCH site2 D
    (8,  2, '2024-04-16', '2026-04-16', 'active'),      -- CMP site2 D (91d -> not expiring)
    (9,  3, '2025-04-15', '2026-04-15', 'active'),      -- WETS site1 A (exactly 90d)
    (10, 3, '2025-04-16', '2026-04-16', 'active');      -- WETS site1 A (91d)

INSERT INTO training_completions (completion_id, tech_id, cert_id, enrolled_date, completed_date, hours_spent) VALUES
    (1, 1, 2, '2024-05-01', '2024-05-20', 24.0),
    (2, 3, 1, '2025-03-01', '2025-04-01', 16.5),
    (3, 6, 2, '2025-10-01', NULL, NULL),
    (4, 7, 1, '2025-01-10', NULL, NULL);   -- stale (enrolled > 120 days before as-of)
