-- ===========================================================================
-- v_parts_consumption
-- Grain: one row per (site_id, part_id, month)
--
-- Monthly consumption quantities from stock_movements (movement_type =
-- 'consumption'; qty_delta is negative for consumption, so it is negated),
-- with a trailing-90-day average daily usage and month-over-month change,
-- both computed with window functions.
--
-- Columns:
--   site_id               site where the consumption happened
--   part_id               part consumed
--   month                 first day of the calendar month
--   consumption_qty       total units consumed in that month
--   avg_daily_usage_90d   avg units/day over the trailing ~90 days
--                         (rolling 3-month sum / 90)
--   mom_change_qty        consumption_qty - previous month's consumption_qty
--   mom_change_pct        mom_change_qty as % of the previous month
--                         (NULL when the previous month is missing or zero)
--
-- Plain view: always computed against live stock_movements.
-- ===========================================================================

DROP VIEW IF EXISTS v_parts_consumption CASCADE;

CREATE VIEW v_parts_consumption AS
WITH monthly AS (
    SELECT
        site_id,
        part_id,
        DATE_TRUNC('month', movement_date)::date AS month,
        SUM(-qty_delta) AS consumption_qty
    FROM stock_movements
    WHERE movement_type = 'consumption'
    GROUP BY site_id, part_id, DATE_TRUNC('month', movement_date)::date
),
lagged AS (
    SELECT
        site_id,
        part_id,
        month,
        consumption_qty,
        LAG(consumption_qty) OVER w AS prev_qty
    FROM monthly
    WINDOW w AS (PARTITION BY site_id, part_id ORDER BY month)
)
SELECT
    site_id,
    part_id,
    month,
    consumption_qty,
    ROUND(SUM(consumption_qty) OVER w / 90.0, 4) AS avg_daily_usage_90d,
    consumption_qty - prev_qty AS mom_change_qty,
    CASE
        WHEN prev_qty IS NULL OR prev_qty = 0 THEN NULL
        ELSE ROUND(100.0 * (consumption_qty - prev_qty) / prev_qty, 2)
    END AS mom_change_pct
FROM lagged
WINDOW w AS (PARTITION BY site_id, part_id ORDER BY month
             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW);
