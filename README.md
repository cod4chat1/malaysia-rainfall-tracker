# Malaysia Rainfall Tracker

Daily, state-level Malaysian rainfall from the free CHIRPS v3 dataset, compiled
into Google Sheets by a scheduled GitHub Actions workflow.

The project covers all 13 states and the federal territories of Kuala Lumpur,
Putrajaya, and Labuan. Its default historical series begins on 2020-01-01 and
it replaces recent preliminary estimates with final values when CHIRPS
publishes them.

## What it costs

The intended hobby deployment costs **RM0**:

- CHIRPS v3 source files are public and free.
- A public GitHub repository can use standard GitHub-hosted Actions runners
  without metered runner charges.
- Standard Google Sheets API use is available without additional cost inside
  its default quota.
- The project uses no AI API, paid weather API, database, hosted server, or
  recurring Codex task after deployment.

Keep the repository public, use only the standard `ubuntu-latest` runner, do not
enable Google Cloud billing for this project, and keep the included safety
limits. Service terms can change; check the current
[GitHub Actions billing](https://docs.github.com/en/actions/concepts/billing-and-usage)
and [Google Sheets API limits](https://developers.google.com/workspace/sheets/api/limits)
occasionally.

The code caps a routine run at 10 source dates, 250 MB of fallback downloads,
and 50 Google API calls. It processes final Cloud-Optimized GeoTIFFs by reading
only the Malaysia window.

## Data method

The canonical series is
[CHIRPS v3 daily Final `rnl`](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/),
which covers 1981 onward. It uses ERA5 to divide CHIRPS pentad rainfall into
daily values.

Recent dates use
[CHIRPS v3 daily Preliminary `sat`](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/).
These use IMERG for daily disaggregation and are labelled
`CHIRPS_V3_PRELIM_SAT`. When the monthly Final data arrives, the same Sheet rows
are replaced with `CHIRPS_V3_FINAL_RNL`.

For each date and area, the tracker reports:

- area-weighted average and median rainfall
- maximum intersecting grid-cell rainfall
- percentage of valid area above 1, 10, 20, and 50 mm
- valid grid-cell count and valid-area percentage
- exact source URL, data status, and processing time

The state-to-grid intersections are calculated once in an equal-area
projection and stored in
`data/chirps_v3_malaysia_weights.npz`. Routine runs perform only small weighted
array calculations.

The vendored administrative boundary is geoBoundaries
`MYS-ADM1-15666254`, based on OpenStreetMap/Wambacher and licensed under ODbL
1.0. See [data/BOUNDARY_ATTRIBUTION.md](data/BOUNDARY_ATTRIBUTION.md).

## Google Sheet tabs

- `Daily_State_Rainfall`: one deterministic row per date and area
- `State_Daily_Matrix`: date rows and 16 state/territory columns
- `Monthly_Summary`: monthly statistics for each area
- `Data_Quality`: execution outcomes and source availability
- `Configuration`: schema, dataset, state ordering, and initialized date

Rows are predetermined from 2020-01-01, with 16 rows per day. A rerun updates
the same rows instead of appending duplicates.

CHIRPS itself extends back to 1981. To maintain deterministic row identities,
the calendar start is fixed when a Sheet is initialized. A separate archival
Sheet can opt into 1981 by setting `RAINFALL_CALENDAR_START=1981-01-01` before
initialization.

## 1. Create the Google Sheet

1. Open [Google Sheets](https://sheets.google.com).
2. Create a blank spreadsheet named `Malaysia Rainfall Tracker`.
3. Copy its ID from the URL:

   `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

The setup command creates the five required tabs. The original blank `Sheet1`
can be deleted manually afterward.

## 2. Create the Google service account

1. Open [Google Cloud Console](https://console.cloud.google.com).
2. Create a project such as `malaysia-rainfall-hobby`.
3. Do not attach a billing account.
4. Open **APIs & Services → Library**.
5. Find and enable **Google Sheets API**.
6. Open **IAM & Admin → Service Accounts**.
7. Create a service account named `rainfall-sheet-writer`.
8. Do not grant it a project role; access comes from sharing the one Sheet.
9. Open the service account, select **Keys → Add key → Create new key → JSON**.
10. Save the downloaded JSON temporarily.
11. Copy the service account's email address.
12. Share the Google Sheet with that email as **Editor**.

The credential is a secret. Never place the JSON file in this repository, an
issue, a screenshot, or a chat message.

## 3. Create the public GitHub repository

1. Create a new **public** repository named `malaysia-rainfall-tracker`.
2. Push this project to it:

```powershell
git branch -M main
git remote add origin https://github.com/YOUR-NAME/malaysia-rainfall-tracker.git
git push -u origin main
```

3. Open the repository's **Settings → Secrets and variables → Actions**.
4. Add these repository secrets:

   - `GOOGLE_SPREADSHEET_ID`: the ID copied from the Sheet URL
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: the entire contents of the downloaded JSON

Secrets are not visible in the public repository.

## 4. Initialize the Sheet

For local setup on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
$env:PYTHONPATH = "src"
$env:GOOGLE_SPREADSHEET_ID = "your-spreadsheet-id"
$env:GOOGLE_SERVICE_ACCOUNT_JSON = Get-Content -Raw "C:\safe\service-account.json"
.\.venv\Scripts\python.exe -m rainfall_tracker.cli init-sheet
```

This creates the date/state skeleton through the current date. Future runs
extend it 31 days at a time. Repeating `init-sheet` is safe, but normally
unnecessary.

Remove the credential variables from the terminal afterward:

```powershell
Remove-Item Env:GOOGLE_SERVICE_ACCOUNT_JSON
Remove-Item Env:GOOGLE_SPREADSHEET_ID
```

## 5. Test without writing

The smoke test contacts CHIRPS, calculates all 16 areas, prints the results, and
does not authenticate to Google:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m rainfall_tracker.cli smoke --date 2025-01-15
```

A successful run prints 16 records and a summary containing
`"processed_dates": 1`.

## 6. First live update

With the Google environment variables set:

```powershell
.\.venv\Scripts\python.exe -m rainfall_tracker.cli run
```

This examines a rolling 62-day window but processes at most 10 missing or
replaceable dates. Missing source dates are normal because CHIRPS Preliminary
is published in pentad batches.

## 7. Historical backfill

Backfills are deliberately split into monthly batches:

```powershell
.\.venv\Scripts\python.exe -m rainfall_tracker.cli backfill `
  --start-date 2020-01-01 `
  --end-date 2020-12-31
```

Recommended order:

1. Backfill 2020 through the latest completed year, one workflow run per year.
2. Confirm the Sheet and monthly summaries.
3. Let the scheduled workflow maintain the current year.

In GitHub, open **Actions → Historical rainfall backfill → Run workflow** and
enter one year. The workflow safely processes at most two independent months
at once, so each job stays small and can be retried independently. Do not launch
overlapping years; the workflow concurrency lock serializes them. The default
deployment rejects dates before 2020-01-01. For the current year, it stops at
yesterday and skips future months automatically.

## 8. Daily automation

`.github/workflows/daily-rainfall.yml` runs at `00:30 UTC`, which is `08:30`
Malaysia time. GitHub schedules can start a little late.

The workflow:

1. checks recent source availability
2. skips already-final dates
3. fills missing Preliminary dates
4. replaces Preliminary with Final
5. updates affected monthly summaries
6. records the result in `Data_Quality`

No new source data is a successful outcome, not an error.

## Commands

```text
rainfall-tracker build-weights
rainfall-tracker init-sheet [--through YYYY-MM-DD]
rainfall-tracker run [--start-date DATE --end-date DATE] [--dry-run]
rainfall-tracker backfill --start-date DATE --end-date DATE [--dry-run]
rainfall-tracker smoke --date DATE
```

The same commands work as:

```text
python -m rainfall_tracker.cli ...
```

when `PYTHONPATH=src`.

## Maintenance

- Review Dependabot proposals monthly; do not merge failing updates.
- Rotate the Google service-account key yearly or immediately after suspected
  exposure.
- After rotation, update `GOOGLE_SERVICE_ACCOUNT_JSON` in GitHub and delete the
  old key in Google Cloud.
- Check `Data_Quality` after backfills or workflow failures.
- If CHIRPS changes its raster grid, the application refuses to process it.
  Review the source change before rebuilding spatial weights.
- If boundary data is intentionally updated, replace the GeoJSON, update its
  attribution, run `build-weights`, review the differences, and commit both
  files together.

## Development verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
```

All automated tests are offline. Live source access is opt-in through `smoke`.

## Limitations

- CHIRPS is a gridded estimate, not an official total from a single Malaysian
  rain gauge.
- Daily CHIRPS is derived from pentad totals. Preliminary and Final products
  use different daily disaggregation inputs, which is why status is explicit.
- A state average can hide localized storms; use the maximum and affected-area
  columns alongside the average.
- Historical boundaries are held constant using the pinned 2017 ADM1 file so
  the time series remains spatially comparable.

## Project design

The approved architecture and acceptance criteria are recorded in
[the design specification](docs/superpowers/specs/2026-07-26-malaysia-rainfall-tracker-design.md).
