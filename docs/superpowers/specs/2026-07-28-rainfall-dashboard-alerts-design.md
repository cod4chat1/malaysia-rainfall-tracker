# Rainfall Dashboard and Alert Design

## Goal

Add an easy-to-read Google Sheets dashboard that supports both state-to-state
comparison and anomaly detection, while changing GitHub notifications so a
successful no-new-data run remains silent.

The existing rainfall source tabs and daily schedule remain authoritative and
unchanged.

## Dashboard Structure

Create two tabs:

- `Dashboard`: the first visible tab and the user-facing overview.
- `Dashboard_Data`: a helper tab containing chart-ready and ranking data.

The pipeline will refresh `Dashboard_Data` from the stored rainfall data after
new dates are written. Charts will use bounded helper ranges instead of applying
large live formulas to the roughly 80,000-row source table.

Future calendar rows with blank rainfall values will not be treated as observed
data. The dashboard's latest date will be the maximum date with valid rainfall.

## Controls

The dashboard will use clear dropdown selectors because they are more reliable
than native pivot slicers for driving several custom moving-average charts:

- `State 1`: focus state and first comparison series.
- `State 2`: optional comparison state.
- `State 3`: optional comparison state.
- `Period`: 90 days, 180 days, 1 year, 3 years, or all available data.
- `Frequency`: daily or monthly where the relevant chart supports both.

Default selections will be Johor, Sabah, and Sarawak over one year. Every
Malaysian state and federal territory remains selectable.

## Metrics and Definitions

The dashboard will display:

- latest valid source date
- source latency in calendar days
- latest focus-state daily rainfall
- 7-day moving average of valid daily rainfall
- 30-day moving average of valid daily rainfall
- current calendar-month rainfall total
- focus-state difference versus its historical seasonal normal

Moving averages are trailing calculations ending on each observation date:

- 7-day moving average: mean of the latest seven valid daily observations
- 30-day moving average: mean of the latest 30 valid daily observations
- 30-day rolling rainfall: sum of the latest 30 valid daily observations

The seasonal normal for a calendar month is the state's average monthly total
for that month across the available 2013-present history, using only complete
months. Incomplete current months are clearly marked and are not compared with
complete historical monthly totals as though they were equivalent.

## Charts and Comparison Views

1. **Focus-state anomaly chart**
   - daily actual rainfall
   - 7-day moving average
   - 30-day moving average

2. **Selected-state comparison chart**
   - 30-day rolling rainfall for State 1, State 2, and State 3

3. **Monthly comparison chart**
   - monthly rainfall totals for the three selected states
   - focus-state historical monthly normal

4. **All-state comparison table**
   - latest 30-day rainfall
   - percentage difference versus seasonal normal
   - rainy days
   - heavy-rain days
   - maximum daily rainfall
   - latest percentage of area above 20 mm

5. **Twelve-month heatmap**
   - rows: all 16 states and federal territories
   - columns: latest 12 complete months
   - color scale: dry to wet using rainfall totals

The styling will follow the ship-traffic workbook's clean layout: hidden
gridlines on dashboard/helper tabs, compact selector panel, neutral KPI cards,
one accent color with muted comparison colors, intentional legends, and no 3D
charts.

## Automation and Sustainability

Dashboard creation and refresh will be implemented in the rainfall tracker,
not as a one-time manual Sheet edit. This ensures a new or repaired workbook can
recreate the dashboard and future updates keep the helper data current.

The helper data will be limited to the ranges needed by the dashboard, keeping
Google Sheets formulas and API requests small. Existing raw and summary tabs
will be preserved.

## Notification Rule

The GitHub alert step will:

- create or comment on the alert issue when `processed_dates > 0`
- create or comment on the alert issue when the rainfall job fails
- skip the alert when the job succeeds and `processed_dates == 0`
- alert on a successful run with an unavailable summary, because the result
  cannot be safely classified as a confirmed no-new-data run

The workflow continues to run every day so delayed CHIRPS dates are detected and
backfilled automatically.

## Failure Handling

- A dashboard refresh failure must fail the rainfall job so incomplete output is
  visible and retried.
- A GitHub alert-delivery failure remains non-blocking and cannot undo rainfall
  rows already written.
- Charts and KPI cells will show a clear unavailable state instead of zero when
  source data is missing.

## Validation

- unit tests for moving averages, rolling totals, latest-valid-date selection,
  seasonal normals, incomplete-month handling, and alert-send decisions
- full existing Python test suite and lint checks
- metadata verification of both new tabs, dropdown validation, chart count and
  titles, helper ranges, hidden gridlines, and preserved existing tabs
- read-back verification of dashboard formulas/values after a live refresh
- visual inspection of the dashboard at normal Google Sheets zoom
- one manual no-new-data workflow run to confirm no alert comment is added
