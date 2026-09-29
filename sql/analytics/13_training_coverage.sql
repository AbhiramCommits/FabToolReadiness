-- ===========================================================================
-- v_training_coverage
-- Grain: one row per (tool_type, site_id, shift)
--
-- Certified-technician coverage against a target of 2 certified techs per
-- shift, built as the full grid of tool_type x site x shift (A-D) so that
-- uncovered combinations show up explicitly instead of disappearing.
--
-- Columns:
--   tool_type                  tool family covered by the certification
--   site_id, shift             coverage cell
--   certified_techs            active technicians at the site holding an
--                              active certification for the tool_type
--   target_techs               target staffing (2 certified per shift)
--   coverage_ratio             certified_techs / target_techs
--   certs_expiring_90d         certs expiring within the next 90 days
--   is_single_point_of_failure exactly one certified tech for the cell
--
-- Materialized view: refreshed in dependency order by 99_refresh.sql.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS v_training_coverage CASCADE;

CREATE MATERIALIZED VIEW v_training_coverage AS
WITH grid AS (
    SELECT c.tool_type, s.site_id, sh.shift
    FROM (SELECT DISTINCT tool_type FROM certifications) c
    CROSS JOIN sites s
    CROSS JOIN (VALUES ('A'), ('B'), ('C'), ('D')) AS sh(shift)
),
certified AS (
    SELECT
        te.site_id,
        c.tool_type,
        te.shift,
        COUNT(DISTINCT tc.tech_id) AS certified_techs,
        COUNT(*) FILTER (
            WHERE tc.expires_date BETWEEN analytics_as_of()
                                     AND analytics_as_of() + INTERVAL '90 days'
        ) AS certs_expiring_90d
    FROM tech_certifications tc
    JOIN technicians te ON te.tech_id = tc.tech_id
    JOIN certifications c ON c.cert_id = tc.cert_id
    WHERE te.is_active AND tc.status = 'active'
    GROUP BY te.site_id, c.tool_type, te.shift
)
SELECT
    g.tool_type,
    g.site_id,
    g.shift,
    COALESCE(c.certified_techs, 0) AS certified_techs,
    2 AS target_techs,
    ROUND(COALESCE(c.certified_techs, 0)::numeric / 2.0, 2) AS coverage_ratio,
    COALESCE(c.certs_expiring_90d, 0) AS certs_expiring_90d,
    (COALESCE(c.certified_techs, 0) = 1) AS is_single_point_of_failure
FROM grid g
LEFT JOIN certified c
       ON c.site_id = g.site_id
      AND c.tool_type = g.tool_type
      AND c.shift = g.shift;

CREATE INDEX idx_v_training_coverage_type_site_shift
    ON v_training_coverage (tool_type, site_id, shift);
