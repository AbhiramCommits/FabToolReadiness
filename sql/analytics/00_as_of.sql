-- ===========================================================================
-- 00_as_of.sql
-- analytics_as_of(): the date the analytics views treat as "now".
--
-- Defaults to CURRENT_DATE. Callers that need a historical or point-in-time
-- snapshot (scripts/export_reports.py --as-of) can override it per session
-- with:
--
--     SET fabtool.as_of = 'YYYY-MM-DD';
--
-- Materialized views must be refreshed with the setting in effect for it to
-- take hold (export_reports.py does this inside a rolled-back transaction).
-- ===========================================================================

CREATE OR REPLACE FUNCTION analytics_as_of()
RETURNS date
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        NULLIF(current_setting('fabtool.as_of', true), '')::date,
        CURRENT_DATE
    );
$$;
