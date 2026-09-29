-- ===========================================================================
-- v_training_throughput
-- Grain: one row per (site_id, month)
--
-- Enrollment-to-completion flow by enrollment month, plus median
-- time-to-certify for completions recorded in that month.
--
-- Columns:
--   site_id, month              enrollment month of the cohort
--   enrolled_count              enrollments in that month
--   completed_count             of those, how many have a completed_date
--   completion_rate             completed_count / enrolled_count
--   median_days_to_certify      PERCENTILE_CONT(0.5) of
--                               completed_date - enrolled_date for
--                               completions recorded in that month
--   stale_in_progress_count     enrollments still incomplete more than
--                               120 days after enrollment
--
-- Plain view: always computed against live training_completions.
-- ===========================================================================

DROP VIEW IF EXISTS v_training_throughput CASCADE;

CREATE VIEW v_training_throughput AS
WITH enrolled AS (
    SELECT
        t.site_id,
        DATE_TRUNC('month', tc.enrolled_date)::date AS month,
        COUNT(*) AS enrolled_count,
        COUNT(*) FILTER (WHERE tc.completed_date IS NOT NULL) AS completed_count,
        COUNT(*) FILTER (WHERE tc.completed_date IS NULL
                          AND tc.enrolled_date < analytics_as_of() - INTERVAL '120 days')
            AS stale_in_progress_count
    FROM training_completions tc
    JOIN technicians t ON t.tech_id = tc.tech_id
    GROUP BY t.site_id, DATE_TRUNC('month', tc.enrolled_date)::date
),
completions AS (
    SELECT
        t.site_id,
        DATE_TRUNC('month', tc.completed_date)::date AS month,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tc.completed_date - tc.enrolled_date)
            AS median_days_to_certify
    FROM training_completions tc
    JOIN technicians t ON t.tech_id = tc.tech_id
    WHERE tc.completed_date IS NOT NULL
    GROUP BY t.site_id, DATE_TRUNC('month', tc.completed_date)::date
)
SELECT
    COALESCE(e.site_id, c.site_id) AS site_id,
    COALESCE(e.month, c.month) AS month,
    COALESCE(e.enrolled_count, 0) AS enrolled_count,
    COALESCE(e.completed_count, 0) AS completed_count,
    ROUND(COALESCE(e.completed_count, 0)::numeric
          / NULLIF(e.enrolled_count, 0), 3) AS completion_rate,
    ROUND(c.median_days_to_certify::numeric, 1) AS median_days_to_certify,
    COALESCE(e.stale_in_progress_count, 0) AS stale_in_progress_count
FROM enrolled e
FULL OUTER JOIN completions c
     ON c.site_id = e.site_id AND c.month = e.month;
