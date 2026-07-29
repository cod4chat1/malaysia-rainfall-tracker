# Rainfall Multi-Select, Regional Aggregates, and Interactive Map Design

## Objective

Improve the Malaysia Rainfall Tracker dashboard so a user can compare any
number of states, inspect national and regional rainfall, distinguish rainfall
level from recent direction, and explore an interactive state-level Malaysia
map without adding a paid data or mapping service.

The canonical CHIRPS state records remain unchanged. New regional series and
visual outputs are derived from the existing state observations during each
dashboard refresh.

## Scope

This change will:

- replace the three comparison dropdowns with native Google Sheets checkboxes;
- retain one focus-area dropdown for single-area headline cards;
- add Malaysia, Peninsular Malaysia, and East Malaysia analysis series;
- add national and regional 7-day and 30-day moving averages;
- replace the current prorated month-to-date comparison with a historical
  day-of-month comparison;
- separate rainfall anomaly from recent trend;
- add a state-level interactive Malaysia map opened inside Google Sheets; and
- preserve the existing automatic refresh and alert behavior.

This change will not alter CHIRPS downloads, raw state rows, historical
backfill identity, email routing, or the free hobby-project cost model.

## Analysis Areas

The dashboard will support 19 areas:

1. the existing 13 states;
2. Kuala Lumpur, Putrajaya, and Labuan;
3. Peninsular Malaysia;
4. East Malaysia; and
5. Malaysia.

Regional membership is:

- **Peninsular Malaysia:** Johor, Kedah, Kelantan, Melaka, Negeri Sembilan,
  Pahang, Penang, Perak, Perlis, Selangor, Terengganu, Kuala Lumpur, and
  Putrajaya.
- **East Malaysia:** Sabah, Sarawak, and Labuan.
- **Malaysia:** all 16 first-level administrative areas.

### Land-area weighting

Regional daily rainfall will be land-area weighted. Each area's effective area
will be derived from the spatial intersection weights already stored in
`data/chirps_v3_malaysia_weights.npz`.

For region \(R\) on day \(d\):

```text
regional_rainfall[d, R] =
    sum(state_rainfall[d, s] * effective_area[s] for s in R)
    / sum(effective_area[s] for s in R)
```

An aggregate is valid only when every constituent state or territory has a
valid observation for the day. This avoids silently biasing a regional result
when a large state is missing.

Derived regional series will be written to dashboard helper data and a visible
`Regional_Daily_Rainfall` tab. The raw `Daily_State_Rainfall` layout will not
be changed.

## Dashboard Controls

### Focus area

A single dropdown will select the focus area for:

- latest rainfall;
- 7-day moving average;
- 30-day moving average;
- month-to-date rainfall;
- month-to-date anomaly;
- recent trend; and
- the focus-area line chart.

The dropdown will contain all 19 analysis areas.

### Comparison selection

The three comparison dropdowns will be replaced with a labelled checkbox grid
containing all 19 analysis areas. A checked box acts as a clickable state or
region button.

- Any number of areas may be checked.
- Selections persist across automated refreshes.
- The comparison helper table and chart update from the checkbox values.
- The default selection is Johor, Sabah, Sarawak, Peninsular Malaysia, East
  Malaysia, and Malaysia.
- If no box is checked, the comparison chart displays a clear instruction
  rather than an error.
- If more than eight areas are selected, a visible note warns that the chart
  may be crowded, but the selection is not blocked.

The period and daily/monthly frequency controls remain.

## Moving Averages and Rolling Rainfall

For every state and aggregate:

- **Daily rainfall:** the area's area-weighted daily rainfall in millimetres.
- **7-day moving average:** arithmetic mean of the latest seven valid
  consecutive calendar-day observations.
- **30-day moving average:** arithmetic mean of the latest 30 valid
  consecutive calendar-day observations.
- **30-day rainfall:** sum of the latest 30 valid consecutive calendar-day
  observations.

Moving calculations require a complete window. Missing calendar days do not
get compressed out of the time series. A window containing a missing day is
blank until a complete window is available.

## Seasonal Normal

The dashboard will display its baseline explicitly, for example:

```text
Seasonal baseline: 2013-2025 complete years
```

For a dashboard date in year \(Y\), the baseline is January 2013 through
December \(Y-1\). The current partial year is excluded from its own baseline.

### Monthly seasonal normal

For an area and calendar month, the monthly seasonal normal is the arithmetic
mean of complete monthly rainfall totals for that same calendar month in the
baseline years.

For July 2026:

```text
July normal = mean(July 2013, July 2014, ..., July 2025)
```

Only months with every required daily observation are included.

### Expected month-to-date rainfall

The current linear proration will be removed. Expected month-to-date rainfall
through day \(k\) is the average historical cumulative rainfall through the
same day of the same calendar month.

For 20 July 2026:

```text
Expected MTD =
    mean(
        cumulative rainfall 1-20 July 2013,
        cumulative rainfall 1-20 July 2014,
        ...,
        cumulative rainfall 1-20 July 2025
    )
```

This respects within-month rainfall seasonality and does not assume rainfall
is evenly distributed through a month.

## Anomaly and Recent Trend

The dashboard will show rainfall level and rainfall direction separately.

### Month-to-date anomaly

```text
MTD anomaly =
    current MTD rainfall / expected historical MTD rainfall - 1
```

Interpretation:

- `+25%` means accumulated rainfall through the current day is 25% above the
  historical expectation for the same point in the month.
- `-25%` means it is 25% below expectation.

This metric does not indicate whether rainfall is currently rising or falling.

### Recent trend

```text
Recent trend percentage = 7-day moving average / 30-day moving average - 1
```

Classification:

- greater than `+10%`: **Rising**;
- from `-10%` through `+10%`: **Stable**; and
- less than `-10%`: **Falling**.

If the 30-day average is zero or a complete moving window is unavailable, the
trend is shown as `Insufficient data`.

The focus cards will be labelled `MTD anomaly vs historical pace` and `Recent
trend (7D vs 30D)` so a positive anomaly cannot be confused with an upward
trend.

## Charts and Tables

The dashboard will contain:

1. **Focus area: actual versus moving averages**
   - daily rainfall;
   - 7-day moving average; and
   - 30-day moving average.
2. **Selected areas comparison**
   - daily mode: rolling 30-day rainfall;
   - monthly mode: monthly rainfall totals;
   - series controlled by the checkbox grid.
3. **Focus area: monthly total versus seasonal normal**
   - actual monthly rainfall; and
   - same-calendar-month seasonal normal.
4. **Current conditions table**
   - all 19 areas;
   - MTD rainfall;
   - expected MTD rainfall;
   - MTD anomaly;
   - 7-day average;
   - 30-day average; and
   - recent trend.
5. **Twelve-month heatmap**
   - all 19 analysis areas; and
   - complete monthly totals.

## Interactive Malaysia Map

### User experience

The spreadsheet will include a `Rainfall Map` menu item that opens an
interactive dialog within Google Sheets.

The dialog will show a custom SVG map generated from
`data/malaysia_adm1.geojson`. It will not call Google Maps or another paid map
provider.

The map will include:

- mainland Malaysia and East Malaysia at readable scales;
- inset or callout treatment for Kuala Lumpur, Putrajaya, and Labuan;
- a visible legend;
- a metric selector; and
- a latest-data timestamp.

Metric choices:

- MTD rainfall;
- MTD anomaly; and
- recent trend percentage.

Color scales:

- MTD rainfall: light-to-dark blue;
- MTD anomaly: brown/orange for dry, neutral grey near normal, blue for wet;
- recent trend: orange for falling, grey for stable, blue for rising; and
- missing data: light grey with hatching or an explicit no-data tooltip.

Hovering over a state or territory displays:

- area name;
- latest valid date;
- MTD rainfall;
- expected historical MTD rainfall;
- MTD anomaly;
- 7-day average;
- 30-day average; and
- rising, stable, falling, or insufficient-data status.

### Implementation boundary

The Python dashboard refresh will write a hidden `Map_Data` tab containing the
latest tooltip values. A bound Google Apps Script will:

- add the `Rainfall Map` menu;
- open an HTML-service dialog;
- read only the bound spreadsheet's `Map_Data` values; and
- render the bundled SVG paths and hover tooltips.

During the build, the administrative GeoJSON will be converted into simplified
static SVG path data sized for the dialog. Runtime map opening will not parse
the full 3.2 MB GeoJSON file or download a boundary file.

There is no Apps Script time trigger and no duplicate data pipeline. GitHub
Actions remains the only scheduled updater.

The map implementation is isolated in repository-owned Apps Script and HTML
files. Removing the map requires deleting the bound script and `Map_Data` tab;
the rainfall data, dashboard calculations, and automation continue to work.

The user will need to approve the bound script's spreadsheet-read permission
once when opening the map for the first time.

The repository will contain the complete Apps Script source and installation
instructions. The implementation session will install the bound script through
the spreadsheet's Apps Script editor where the connected Google account permits
it. If Google requires an account-level authorization screen, the user performs
only that approval step; no credential or API key is copied into the script.

## Data Flow

```text
Existing state rainfall rows
        |
        v
Dashboard aggregation module
        |
        +--> state + regional daily series
        +--> moving averages and rolling totals
        +--> monthly normals and historical MTD pace
        +--> anomaly and trend classifications
        |
        v
Dashboard_Data + Regional_Daily_Rainfall + Map_Data
        |
        +--> native Google Sheets cards, tables, heatmap, and charts
        |
        +--> bound Apps Script interactive SVG map
```

## Error Handling

- Missing constituent state data makes the corresponding regional value blank.
- Missing historical comparison data produces `Insufficient data`, not zero.
- A focus area that lacks data keeps the controls visible and displays a clear
  unavailable-data message.
- No checked comparison area produces an instruction instead of a chart error.
- Apps Script map failure does not affect rainfall ingestion or dashboard
  refresh.
- The map dialog displays a readable message if `Map_Data` is missing or stale.
- Existing checkbox and focus selections are preserved during refresh.

## Cost and Sustainability

- CHIRPS remains the only rainfall source.
- No Google Maps API key is required.
- Apps Script, Google Sheets, GitHub Actions, GeoJSON, and generated SVG assets
  are used within their free hobby-project paths.
- The scheduled updater does not invoke AI.
- Aggregate and climatology calculations run locally in the existing Python
  workflow.
- The Apps Script runs only when the user opens or interacts with the map.

## Testing and Verification

Automated tests will cover:

- regional membership;
- effective-area-weighted aggregation;
- aggregate invalidation when a constituent state is missing;
- calendar-day moving windows with gaps;
- fixed prior-year seasonal baseline selection;
- same-day-of-month expected MTD rainfall;
- anomaly percentage;
- trend percentage and classification thresholds;
- checkbox selection preservation;
- comparison helper output for zero, one, and many selections;
- map-data schema and missing-data behavior; and
- GeoJSON-to-SVG state-name matching for all 16 areas.

Live verification will cover:

- all 19 checkboxes and focus-area choices;
- charts updating after checkbox changes;
- Malaysia, Peninsular Malaysia, and East Malaysia series;
- headline anomaly and trend labels;
- map rendering of all 16 areas;
- hover details for large areas and the three small territories;
- metric color changes;
- selection persistence after a dashboard-only workflow refresh; and
- no regression in daily updates or notification behavior.
