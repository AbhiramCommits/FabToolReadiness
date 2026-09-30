# Tableau Guide: Publishing the Fab Tool Readiness Dashboard

Step-by-step instructions for building and publishing the dashboard to
Tableau Public from the flat files in `exports/tableau/`.

## 0. Generate the exports

```sh
make all            # refresh -> quality checks -> export CSVs + Excel
```

You need these five files from `exports/tableau/`:

| File | Grain | Key fields |
|---|---|---|
| `tool_readiness.csv` | tool | `tool_code`, `site_code`, `tool_type`, `process_area`, `criticality`, `readiness_score`, `risk_band`, `top_reason` |
| `inventory_health.csv` | site x part | `site_code`, `part_number`, `on_hand_qty`, `reorder_point`, `safety_stock`, `lead_time_days`, `unit_cost`, `days_of_supply`, `is_stockout`, `is_excess`, `excess_value_usd` |
| `parts_consumption.csv` | site x part x month | `site_code`, `part_number`, `month`, `consumption_qty`, `avg_daily_usage_90d` |
| `training_coverage.csv` | tool_type x site x shift | `site_code`, `tool_type`, `shift`, `certified_techs`, `target_techs`, `coverage_ratio`, `certs_expiring_90d`, `is_single_point_of_failure` |
| `training_throughput.csv` | site x month | `site_code`, `month`, `enrolled_count`, `completed_count`, `completion_rate`, `median_days_to_certify`, `stale_in_progress_count` |

Every file carries a `snapshot_date` column (the as-of date).

## 1. Connect and define relationships

1. Tableau Public → **New** → **Connect** → **Text file**, select the five
   CSVs (Tableau unions/joins them per connection; add each as its own
   connection, then drag them onto the relationship canvas).
2. Go to **Data Source** and create relationships:
   - `tool_readiness` ↔ `inventory_health` on **`site_code = site_code`**
     (a tool's parts live at the tool's site; many-to-many).
   - `tool_readiness` ↔ `training_coverage` on
     **`site_code = site_code` AND `tool_type = tool_type`**.
   - `inventory_health` ↔ `parts_consumption` on
     **`site_code = site_code` AND `part_number = part_number`**.
   - Leave cardinality as *Many (may) to Many*; Tableau resolves the
     measures contextually per worksheet.
3. Create these **calculated fields** (copy-pasteable Tableau syntax):

```
[At Risk Flag]
IF [risk_band] = 'critical' OR [risk_band] = 'at_risk'
THEN 'at risk' ELSE 'ok' END

[Coverage %]
SUM([certified_techs]) / SUM([target_techs])

[DOS Band]
IF ISNULL([days_of_supply]) THEN 'no usage'
ELSEIF [days_of_supply] = 0 THEN 'stockout'
ELSEIF [days_of_supply] < 30 THEN '< 30 days'
ELSEIF [days_of_supply] < 90 THEN '30-90 days'
ELSEIF [days_of_supply] <= 365 THEN '90-365 days'
ELSE '> 365 days' END

[Reorder Signal]
IF [on_hand_qty] < [reorder_point] THEN 1 ELSE 0 END

[Expiring Flag]
IF [certs_expiring_90d] > 0 THEN 'expiring' ELSE 'ok' END
```

## 2. Build the five worksheets

### WS1 — At-Risk Tools (ranked bar)
- Data: `tool_readiness`. Filter `[At Risk Flag] = 'at risk'`.
- Rows: `tool_code` (right-click → Sort → by `SUM(readiness_score)`
  ascending). Columns: `SUM(readiness_score)`.
- Color: `risk_band` (critical = red, at_risk = orange). Tooltip:
  `tool_type`, `process_area`, `top_reason`.

### WS2 — Readiness Heatmap by Process Area
- Data: `tool_readiness`. Columns: `process_area`. Rows: `tool_type`.
- Mark: Square. Color: `AVG(readiness_score)` (diverging palette, reversed).
- Label: `AVG(readiness_score)` (1 decimal). Tooltip: `COUNT(tool_code)`.

### WS3 — Days of Supply Distribution
- Data: `inventory_health`. Columns: `[DOS Band]` (in order: stockout,
  < 30, 30-90, 90-365, > 365). Rows: `COUNT(part_number)`.
- Color: `[DOS Band]`, with 'stockout' fixed to red. Filter out
  `is_excess = FALSE` if you only want problem bins.

### WS4 — Cert Coverage by Shift (matrix)
- Data: `training_coverage`. Columns: `shift`. Rows: `tool_type`,
  then `site_code`.
- Mark: Square. Color: `AVG([Coverage %])` (red below 50%, green at 100%).
- Label: `AVG([Coverage %])`. Tooltip: `SUM(certified_techs)`,
  `SUM(certs_expiring_90d)`.

### WS5 — Monthly Consumption Trend with Reorder Events
- Data: `parts_consumption` (related to `inventory_health`).
- Columns: `month` (continuous). Rows: `SUM(consumption_qty)` (line).
- Add a reference line: `AVG(reorder_point)` (band), labeled
  'average reorder point'.
- Drag `SUM([Reorder Signal])` onto a second axis (right-click the pill →
  Dual Axis), mark it as circles; this flags months/parts where the bin
  sits below its reorder point and an order should have been placed.

## 3. Dashboard layout

Create a **Dashboard (1200 x 800)**, then:

1. Add a horizontal **container** at the top and drop `site_code`,
   `process_area`, and `risk_band` into it as global filters
   (Apply to Worksheets → **All Using Related Data Sources**).
2. Layout:
   - Top-left: WS1 (At-Risk Tools), ~60% width.
   - Top-right: WS2 (Readiness Heatmap), ~40% width.
   - Middle-left: WS3 (Days of Supply Distribution).
   - Middle-right: WS4 (Cert Coverage by Shift).
   - Bottom (full width): WS5 (Monthly Consumption Trend).
3. Add a title text object: *"Fab Tool Readiness — data as of `<snapshot_date>`"*
   (use the `MAX(snapshot_date)` value from any sheet).
4. Set filter actions: clicking a tool in WS1 filters WS2/WS5
   (Dashboard → Actions → Filter).

## 4. Publish to Tableau Public

1. **Server → Tableau Public → Save to Tableau Public…**
2. Sign in to (or create) your Tableau Public account.
3. Name the workbook `Fab Tool Readiness`, add a short description, and
   click **Publish**.
4. Open the published dashboard, copy the URL from the address bar, and
   paste it into the README's Tableau Public link placeholder
   (`<!-- TODO: paste published URL -->`).

> Tip: re-publish after every `make all` so the dashboard tracks the latest
> refresh date; the data is static CSVs, so Tableau Public treats each
> publish as a new extract.
