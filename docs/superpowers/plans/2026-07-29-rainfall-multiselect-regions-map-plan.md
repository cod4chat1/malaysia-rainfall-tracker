# Rainfall Multi-Select, Regions, and Map Implementation Plan

## Goal

Deliver the approved multi-select dashboard, land-area-weighted Malaysia
aggregates, improved seasonal comparisons, separate trend indicators, and a
reversible interactive Malaysia map without changing canonical state rainfall
records or adding paid services.

## Task 1: Regional analysis primitives

Files:

- modify `src/rainfall_tracker/constants.py`
- add `src/rainfall_tracker/regions.py`
- add `tests/test_regions.py`

Steps:

1. Define the 19-area analysis order and exact regional membership.
2. Load state effective areas by summing the existing NPZ area weights.
3. Add a pure function that derives the three regional values for one complete
   state-value mapping.
4. Reject missing constituent states rather than renormalizing a partial
   region.
5. Test membership, area totals, weighted results, and missing-state behavior.

## Task 2: Calendar-safe analytics and climatology

Files:

- add `src/rainfall_tracker/climatology.py`
- modify `src/rainfall_tracker/dashboard.py`
- replace and extend `tests/test_dashboard.py`
- add `tests/test_climatology.py`

Steps:

1. Parse the state daily matrix into a calendar-indexed state table.
2. Derive Malaysia, Peninsular Malaysia, and East Malaysia for every complete
   day.
3. Replace compressed observation windows with consecutive-calendar-day
   moving windows.
4. Compute daily rainfall, MA7, MA30, and rolling-30 totals for all 19 areas.
5. Use 2013 through the prior completed year as the current climatology
   baseline.
6. Compute monthly normals from complete same-calendar-month totals.
7. Compute historical expected MTD rainfall through the same day-of-month.
8. Compute MTD anomaly and MA7-versus-MA30 trend percentage/classification.
9. Extend the dashboard snapshot with current-condition, regional-daily, map,
   and 19-area heatmap outputs.
10. Test gaps, leap dates, incomplete baseline months, zero denominators, and
    trend thresholds.

## Task 3: Google Sheets structure and controls

Files:

- modify `src/rainfall_tracker/sheets.py`
- modify `src/rainfall_tracker/cli.py`
- modify `tests/test_sheets.py`

Steps:

1. Add and format `Regional_Daily_Rainfall`.
2. Add and hide `Map_Data`.
3. Replace comparison dropdowns with a 19-area checkbox grid.
4. Preserve checkbox values and the focus/period/frequency controls by key
   during refresh.
5. Extend the focus dropdown to all 19 areas.
6. Write the fixed baseline label, clearer anomaly label, and trend card.
7. Write current-condition and 19-area heatmap tables.
8. Generate helper formulas for focus and multi-select charts.
9. Replace or update existing chart specs without duplicating charts.
10. Display a no-selection message and a more-than-eight-series readability
    warning.
11. Keep dashboard refresh within the configured Sheets request budget.
12. Test control preservation, formulas, sheet creation, chart specs, and
    request counts with fake services.

## Task 4: Interactive map data and assets

Files:

- add `tools/generate_map_asset.py`
- add `apps_script/Code.gs`
- add `apps_script/MapDialog.html`
- add `apps_script/appsscript.json`
- add generated `apps_script/MapPaths.html`
- add `tests/test_map_asset.py`

Steps:

1. Load and normalize all 16 state geometries from
   `data/malaysia_adm1.geojson`.
2. Simplify geometry for a lightweight static SVG asset.
3. Generate separate readable Peninsular and East Malaysia panels.
4. Add insets or callouts for Kuala Lumpur, Putrajaya, and Labuan.
5. Verify all state names match the canonical order.
6. Add Apps Script menu and dialog functions that read only `Map_Data`.
7. Render MTD, anomaly, and trend color scales.
8. Render state hover tooltips with all approved metrics.
9. Add no-data and stale-data messages.
10. Test deterministic asset generation, state coverage, escaping, and map-data
    schema.

## Task 5: Documentation and local verification

Files:

- modify `README.md`
- modify `.github/workflows/daily-rainfall.yml` only if map installation or
  dashboard-only refresh needs an additional supported mode

Steps:

1. Document regional definitions and weighting.
2. Document seasonal normal, expected MTD, anomaly, and trend formulas.
3. Document checkbox usage and chart-crowding guidance.
4. Document the map permission and removal steps.
5. Run Ruff, Pytest, diff checks, and Apps Script JavaScript syntax checks.
6. Confirm the working tree contains only intended changes.

## Task 6: Publish and live verification

Steps:

1. Commit the implementation on an `agent/` branch.
2. Push and open a draft pull request.
3. Wait for repository checks and merge only when clean.
4. Run the dashboard-only GitHub Actions workflow.
5. Verify exact live tab names, formulas, validations, chart titles, checkbox
   values, conditional formatting, and helper outputs.
6. Install the bound Apps Script through the spreadsheet's Apps Script editor.
7. Ask the user only for the one-time Google permission approval if Google
   presents it.
8. Test checkbox changes, all three regional series, chart updates, map hover,
   metric switching, small-territory insets, and selection persistence.
9. Re-run a dashboard refresh and verify the controls and map still work.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
git diff --check
```

Apps Script files will also be parsed with Node where their syntax is
standalone JavaScript. Template HTML will be checked for required element IDs,
state names, and escaped embedded data.
