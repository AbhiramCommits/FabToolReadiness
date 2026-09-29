-- ===========================================================================
-- v_inventory_health
-- Grain: one row per (site_id, part_id)
--
-- On-hand inventory vs reorder policy, joined to the latest trailing-90-day
-- usage from v_parts_consumption and to 180-day consumption history, to
-- derive days of supply and health flags.
--
-- Columns:
--   site_id, part_id, part_number
--   on_hand_qty            current on-hand units
--   reorder_point          policy reorder point
--   safety_stock           policy safety stock
--   unit_cost              part unit cost (used for excess valuation)
--   avg_daily_usage_90d    latest trailing-90-day avg daily usage (0 if none)
--   days_of_supply         on_hand_qty / avg_daily_usage (NULL when no usage)
--   last_consumption_date  most recent consumption within 180 days
--   consumption_qty_180d   units consumed in the trailing 180 days
--   last_counted_date      when the bin was last cycle-counted
--   is_stockout            on_hand_qty = 0
--   is_below_reorder       on_hand_qty > 0 and below reorder_point
--   is_excess              days_of_supply > 365, or zero usage in 180 days
--                          while still holding stock (obsolete)
--   excess_value_usd       on_hand_qty * unit_cost for excess rows, else 0
--
-- Materialized view: refreshed in dependency order by 99_refresh.sql.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS v_inventory_health CASCADE;

CREATE MATERIALIZED VIEW v_inventory_health AS
WITH usage_180d AS (
    SELECT
        site_id,
        part_id,
        SUM(-qty_delta) AS consumption_qty_180d,
        MAX(movement_date) AS last_consumption_date
    FROM stock_movements
    WHERE movement_type = 'consumption'
      AND movement_date >= CURRENT_DATE - INTERVAL '180 days'
    GROUP BY site_id, part_id
),
latest_usage AS (
    SELECT DISTINCT ON (site_id, part_id)
        site_id,
        part_id,
        avg_daily_usage_90d
    FROM v_parts_consumption
    ORDER BY site_id, part_id, month DESC
),
combined AS (
    SELECT
        i.site_id,
        i.part_id,
        p.part_number,
        p.unit_cost,
        i.on_hand_qty,
        i.reorder_point,
        i.safety_stock,
        i.last_counted_date,
        COALESCE(lu.avg_daily_usage_90d, 0) AS avg_daily_usage_90d,
        u.consumption_qty_180d,
        u.last_consumption_date,
        i.on_hand_qty / NULLIF(lu.avg_daily_usage_90d, 0) AS days_of_supply
    FROM inventory i
    JOIN parts p ON p.part_id = i.part_id
    LEFT JOIN latest_usage lu
           ON lu.site_id = i.site_id AND lu.part_id = i.part_id
    LEFT JOIN usage_180d u
           ON u.site_id = i.site_id AND u.part_id = i.part_id
)
SELECT
    site_id,
    part_id,
    part_number,
    on_hand_qty,
    reorder_point,
    safety_stock,
    unit_cost,
    ROUND(avg_daily_usage_90d, 4) AS avg_daily_usage_90d,
    ROUND(days_of_supply, 2) AS days_of_supply,
    last_consumption_date,
    COALESCE(consumption_qty_180d, 0) AS consumption_qty_180d,
    last_counted_date,
    (on_hand_qty = 0) AS is_stockout,
    (on_hand_qty > 0 AND on_hand_qty < reorder_point) AS is_below_reorder,
    ((days_of_supply IS NOT NULL AND days_of_supply > 365)
     OR (on_hand_qty > 0 AND COALESCE(consumption_qty_180d, 0) = 0)) AS is_excess,
    CASE
        WHEN ((days_of_supply IS NOT NULL AND days_of_supply > 365)
              OR (on_hand_qty > 0 AND COALESCE(consumption_qty_180d, 0) = 0))
        THEN ROUND(on_hand_qty * unit_cost, 2)
        ELSE 0.00
    END AS excess_value_usd
FROM combined;

CREATE INDEX idx_v_inventory_health_site_part
    ON v_inventory_health (site_id, part_id);
