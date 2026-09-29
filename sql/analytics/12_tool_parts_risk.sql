-- ===========================================================================
-- v_tool_parts_risk
-- Grain: one row per tool (tool_id)
--
-- Joins each tool's BOM to the site/part inventory health snapshot and rolls
-- the health flags up into a per-tool parts-risk picture.
--
-- Columns:
--   tool_id, tool_code, site_id, tool_type, process_area, criticality
--   bom_part_count         parts on the tool BOM
--   stocked_out_parts      BOM parts with zero on-hand at the tool's site
--   below_reorder_parts    BOM parts with on_hand below reorder point
--   min_days_of_supply     lowest days of supply across the BOM
--   parts_risk_score       0-100, higher is worse; stockouts are weighted
--                          heaviest and scaled by part lead time
--
-- Materialized view: refreshed in dependency order by 99_refresh.sql.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS v_tool_parts_risk CASCADE;

CREATE MATERIALIZED VIEW v_tool_parts_risk AS
WITH bom_health AS (
    SELECT
        t.tool_id,
        tb.part_id,
        p.lead_time_days,
        ih.days_of_supply,
        ih.is_stockout,
        ih.is_below_reorder
    FROM tools t
    JOIN tool_bom tb ON tb.tool_id = t.tool_id
    JOIN parts p ON p.part_id = tb.part_id
    JOIN v_inventory_health ih
         ON ih.site_id = t.site_id AND ih.part_id = tb.part_id
),
scored AS (
    SELECT
        tool_id,
        COUNT(*) AS bom_part_count,
        COUNT(*) FILTER (WHERE is_stockout) AS stocked_out_parts,
        COUNT(*) FILTER (WHERE is_below_reorder) AS below_reorder_parts,
        MIN(days_of_supply) AS min_days_of_supply,
        LEAST(100,
            SUM(CASE
                WHEN is_stockout THEN 10.0 * (1.0 + lead_time_days / 90.0)
                WHEN is_below_reorder THEN 4.0 * (1.0 + lead_time_days / 90.0)
                WHEN days_of_supply < 30 THEN 2.0
                ELSE 0.0
            END)
        ) AS parts_risk_score
    FROM bom_health
    GROUP BY tool_id
)
SELECT
    t.tool_id,
    t.tool_code,
    t.site_id,
    t.tool_type,
    t.process_area,
    t.criticality,
    s.bom_part_count,
    s.stocked_out_parts,
    s.below_reorder_parts,
    ROUND(s.min_days_of_supply, 2) AS min_days_of_supply,
    ROUND(s.parts_risk_score, 1) AS parts_risk_score
FROM scored s
JOIN tools t ON t.tool_id = s.tool_id;

CREATE INDEX idx_v_tool_parts_risk_tool ON v_tool_parts_risk (tool_id);
