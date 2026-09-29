-- ===========================================================================
-- v_tool_readiness
-- Grain: one row per tool (tool_id)
--
-- Combines the parts-risk score (v_tool_parts_risk) and a training-risk
-- score derived from shift-level certification coverage (v_training_coverage)
-- into a 0-100 readiness score. Risk is additionally weighted up by tool
-- criticality: the same risk lowers readiness more on a more critical tool.
--
-- Columns:
--   tool_id, tool_code, site_id, tool_type, process_area, criticality
--   parts_risk_score         from v_tool_parts_risk (0-100)
--   training_risk_score      0-100 from coverage gaps per shift
--   readiness_score          100 - (0.55 * parts_risk + 0.45 * training_risk)
--                            scaled by criticality factor 1.0-1.4, floor 0
--   risk_band                critical / at_risk / watch / healthy
--   top_reason               text summary of the dominant risk driver
--
-- Materialized view: refreshed in dependency order by 99_refresh.sql.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS v_tool_readiness CASCADE;

CREATE MATERIALIZED VIEW v_tool_readiness AS
WITH coverage_by_type AS (
    SELECT
        site_id,
        tool_type,
        COUNT(*) FILTER (WHERE certified_techs = 0) AS uncovered_shifts,
        COUNT(*) FILTER (WHERE certified_techs = 1) AS spof_shifts,
        SUM(certs_expiring_90d) AS certs_expiring_90d
    FROM v_training_coverage
    GROUP BY site_id, tool_type
),
scored AS (
    SELECT
        t.tool_id,
        t.tool_code,
        t.site_id,
        t.tool_type,
        t.process_area,
        t.criticality,
        pr.parts_risk_score,
        pr.stocked_out_parts,
        pr.below_reorder_parts,
        LEAST(100,
              COALESCE(cov.uncovered_shifts, 4) * 20
            + COALESCE(cov.spof_shifts, 0) * 10
            + LEAST(COALESCE(cov.certs_expiring_90d, 0), 10) * 2
        ) AS training_risk_score,
        COALESCE(cov.uncovered_shifts, 4) AS uncovered_shifts,
        COALESCE(cov.spof_shifts, 0) AS spof_shifts,
        COALESCE(cov.certs_expiring_90d, 0) AS certs_expiring_90d
    FROM tools t
    JOIN v_tool_parts_risk pr ON pr.tool_id = t.tool_id
    LEFT JOIN coverage_by_type cov
           ON cov.site_id = t.site_id AND cov.tool_type = t.tool_type
),
with_readiness AS (
    SELECT
        *,
        GREATEST(0,
            100 - (0.55 * parts_risk_score + 0.45 * training_risk_score)
                * (1.0 + (criticality - 1) * 0.1)
        ) AS readiness_score
    FROM scored
)
SELECT
    tool_id,
    tool_code,
    site_id,
    tool_type,
    process_area,
    criticality,
    ROUND(parts_risk_score, 1) AS parts_risk_score,
    ROUND(training_risk_score::numeric, 1) AS training_risk_score,
    ROUND(readiness_score::numeric, 1) AS readiness_score,
    CASE
        WHEN readiness_score < 30 THEN 'critical'
        WHEN readiness_score < 55 THEN 'at_risk'
        WHEN readiness_score < 75 THEN 'watch'
        ELSE 'healthy'
    END AS risk_band,
    CASE
        WHEN readiness_score >= 75 THEN 'no material issues'
        WHEN stocked_out_parts > 0
             AND 0.55 * parts_risk_score >= 0.45 * training_risk_score
            THEN 'parts: ' || stocked_out_parts || ' BOM part(s) stocked out'
        WHEN below_reorder_parts > 0
             AND 0.55 * parts_risk_score >= 0.45 * training_risk_score
            THEN 'parts: ' || below_reorder_parts || ' BOM part(s) below reorder point'
        WHEN uncovered_shifts > 0
            THEN 'training: ' || uncovered_shifts || ' shift(s) with zero certified techs'
        WHEN spof_shifts > 0
            THEN 'training: ' || spof_shifts || ' shift(s) with a single certified tech'
        WHEN certs_expiring_90d > 0
            THEN 'training: ' || certs_expiring_90d || ' cert(s) expiring within 90 days'
        WHEN parts_risk_score > 0
            THEN 'parts: low days of supply'
        ELSE 'no material issues'
    END AS top_reason
FROM with_readiness;

CREATE INDEX idx_v_tool_readiness_tool ON v_tool_readiness (tool_id);
CREATE INDEX idx_v_tool_readiness_band ON v_tool_readiness (risk_band);
