# Findings: Fab Tool Readiness — Operations Readout

*Data as of **2026-09-29** (regenerated at 2026-09-29 17:09 by `make all`).
Every figure below is computed from the fabtoolreadiness database by
`scripts/refresh_all.py`; the metric formulas are in the README.*

## Executive Summary

- **120 of 250 tools (48%) are flagged
  critical or at-risk for downtime readiness** — 19 critical,
  101 at-risk. These tools need attention before the next
  stockout or certification gap becomes a tool-down event.
- **Spare parts are the dominant risk driver.** 72 of
  480 part/site inventory bins are at zero stock, which exposes
  208 tools (83%). Meanwhile
  $210,635 sits idle in 14 excess or obsolete bins.
- **Training coverage is patchy, and getting worse.** Only 68.1%
  of tool-type/site/shift cells meet the 2-certified-technician target, and
  269 certifications expire within 90 days (27% of
  active certs).

## Key Findings

### 1. Parts risk: 72 bins at zero, 176 more below reorder

208 of 250 tools carry at least one
stocked-out part on their bill of materials, meaning a single unexpected
failure now has no spare to replace it with. Replenishment lead times matter
here: stocked-out parts with a lead time of 45+ days account for
11 of the zero-stock bins and touch 55
tools.
*Chart reference: Excel tracker → Reorder Tracker sheet; Tableau worksheet
"Days of Supply Distribution".*

### 2. Training coverage: 68.1% of cells meet target, shift D at 0.35

Coverage is uneven across the schedule. Shift A averages 3.96
coverage versus 0.35 on shift D, where 21
tool-type/site cells have no certified technician at all and 25
cells rely on a single technician (single point of failure). The thinnest
tool families are CMP (0.34) and AMHS
(0.56). 269 certifications expire within 90 days,
and 1,084 in-progress enrollments have been sitting
incomplete for more than 120 days.
*Chart reference: Excel tracker → Training Tracker sheet; Tableau worksheet
"Cert Coverage by Shift".*

### 3. Combined readiness: 19 critical, 101 at-risk

Blending parts and training risk per tool (55/45, weighted by criticality),
120 tools land below the 55-point readiness line. The worst
concentrations are in the CMP and AMHS fleets, where
thin certification coverage compounds with spare-parts exposure.
*Chart reference: Excel tracker → At-Risk Tools sheet; Tableau worksheets
"At-Risk Tools" and "Readiness Heatmap".*

## Top 10 At-Risk Tools

Ranked by readiness score (lower = worse), as of 2026-09-29:

| Rank | Tool | Site | Type | Crit | Readiness | Band | Top reason |
|---|---|---|---|---|---|---|---|
| 1 | CMP-SGP-003 | SGP | CMP | 5 | 2.7 | critical | parts: 3 BOM part(s) stocked out |
| 2 | CMP-DRS-007 | DRS | CMP | 2 | 12.0 | critical | parts: 6 BOM part(s) stocked out |
| 3 | AMHS-ATX-002 | ATX | AMHS | 4 | 12.2 | critical | parts: 4 BOM part(s) stocked out |
| 4 | CMP-SGP-002 | SGP | CMP | 3 | 13.7 | critical | parts: 3 BOM part(s) stocked out |
| 5 | CMP-DRS-006 | DRS | CMP | 4 | 15.3 | critical | parts: 4 BOM part(s) stocked out |
| 6 | CVD-DRS-005 | DRS | CVD | 3 | 17.8 | critical | parts: 7 BOM part(s) stocked out |
| 7 | WETS-DRS-002 | DRS | WETS | 3 | 19.0 | critical | parts: 5 BOM part(s) stocked out |
| 8 | LITHO-SGP-005 | SGP | LITHO | 3 | 19.2 | critical | parts: 6 BOM part(s) stocked out |
| 9 | CMP-HSZ-005 | HSZ | CMP | 5 | 19.8 | critical | parts: 3 BOM part(s) stocked out |
| 10 | WETS-SGP-002 | SGP | WETS | 5 | 22.2 | critical | parts: 5 BOM part(s) stocked out |

## Recommendations

1. **Restock the long-lead stockouts first.** 11 stocked-out
   bins involve parts with ≥45-day lead times, affecting 55
   tools. A one-time order up to reorder point + safety stock costs
   ≈$754,200 and removes the single largest source of parts risk.
2. **Close the D-shift coverage gap.** Shift D averages 0.35
   coverage vs 3.96 on shift A; 21 D-shift
   cells have zero certified techs. Certifying 54 additional
   technicians (2 per uncovered cell) brings every cell to target.
3. **Renew certifications before they lapse.** 269 certs expire
   within 90 days and median time-to-certify is 29.0 days — start
   renewals this month. Each lapse can turn a covered cell into a
   single-point-of-failure (25 cells already are one).
4. **Free up the 14 excess bins.** $210,635 in obsolete
   or >365-day stock can be scrapped, returned, or transferred to cover the
   replenishment spend in recommendation 1.

## Assumptions & Limitations

- The dataset is synthetic (deterministically seeded), generated to exhibit
  realistic demand seasonality, stockouts, and coverage patterns; treat the
  figures as directional, not measurements.
- Readiness blending (0.55 parts / 0.45 training), criticality scaling
  (1.0–1.4), and band cutoffs (30/55/75) are model choices documented in
  the README.
- Days of supply uses the trailing-90-day average daily usage; bins with no
  usage history have no days-of-supply value.
- The 2-certified-tech-per-shift coverage target is a policy assumption, not
  a measured requirement.
- Median time-to-certify covers completed trainings only; in-progress
  enrollments are reported separately as stale.
