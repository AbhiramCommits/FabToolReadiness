-- ===========================================================================
-- 99_refresh.sql
-- Refresh all materialized views in dependency order:
--
--   1. v_inventory_health   (reads v_parts_consumption, a plain view)
--   2. v_tool_parts_risk    (reads v_inventory_health)
--   3. v_training_coverage  (reads base tables only)
--   4. v_tool_readiness     (reads v_tool_parts_risk + v_training_coverage)
--
-- v_parts_consumption and v_training_throughput are plain views and are
-- always live; they never need refreshing.
-- ===========================================================================

REFRESH MATERIALIZED VIEW v_inventory_health;
REFRESH MATERIALIZED VIEW v_tool_parts_risk;
REFRESH MATERIALIZED VIEW v_training_coverage;
REFRESH MATERIALIZED VIEW v_tool_readiness;
