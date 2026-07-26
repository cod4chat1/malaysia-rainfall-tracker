# Malaysia Rainfall Tracker — Design Specification

Date: 2026-07-26  
Status: Approved design, pending written-spec review

## 1. Objective

Build a zero-cost personal project that calculates daily rainfall statistics for
Malaysia's 13 states and 3 federal territories, stores the results in Google
Sheets, defaults to historical backfill from 2020-01-01, and updates
automatically.

The deployed workflow must not use an AI API, a paid weather API, a database
service, or a permanently running server. Routine operation must not require
Codex or consume language-model tokens.

## 2. Cost and sustainability constraints

- Use the freely available UCSB Climate Hazards Center CHIRPS archive.
- Use standard Google Sheets API calls within the default quota. Do not request
  quota increases and do not require a billing account.
- Use a public GitHub repository and a standard Linux GitHub-hosted runner.
- Set workflow timeouts, concurrency controls, bounded date ranges, and a
  per-run Google API request ceiling to prevent runaway use.
- Do not upload workflow artifacts or retain downloaded rasters after a run.
- Batch Google Sheets reads and writes. Normal daily operation should use a
  small, fixed number of API requests.
- Pin direct Python dependencies and use Dependabot for low-frequency update
  proposals rather than automatic breaking upgrades.

These controls make the intended use free under the service terms and quotas
available when this specification was written. Third-party terms can change, so
the README must explain how to verify the current limits.

## 3. Source data

### 3.1 Primary series

Use CHIRPS v3.0 daily `rnl` Final at 0.05-degree resolution as the canonical
historical series. The source covers 1981 onward and uses ERA5 to disaggregate
CHIRPS pentad totals into daily values. This project starts its default Sheet
series at 2020-01-01.

Final archive:

`https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/`

Cloud-Optimized GeoTIFF archive:

`https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/cogs/{year}/`

The downloader will discover available filenames from the official directory
listing and validate the raster's CRS, transform, dimensions, resolution, data
type, and nodata value before processing. It will not scrape a presentation
website.

### 3.2 Recent preliminary data

Use CHIRPS v3.0 daily `sat` Preliminary for dates not yet present in the Final
archive:

`https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/{year}/`

Preliminary daily files use IMERG for daily disaggregation and are normally
published in pentad batches. Every preliminary row is labelled
`CHIRPS_V3_PRELIM_SAT`. A later scheduled run replaces it with
`CHIRPS_V3_FINAL_RNL` when Final is published. Preliminary and Final values are
never silently blended.

### 3.3 Boundaries

Vendor a pinned Malaysia ADM1 GeoJSON from geoBoundaries `gbOpen`, with its
release metadata and Open Data Commons Open Database License 1.0 attribution.
Runtime jobs must not depend on the geoBoundaries API.

The build must validate and normalize exactly these 16 areas:

Johor, Kedah, Kelantan, Melaka, Negeri Sembilan, Pahang, Penang, Perak, Perlis,
Sabah, Sarawak, Selangor, Terengganu, Kuala Lumpur, Putrajaya, and Labuan.

## 4. Spatial calculation

Precompute the intersection of each administrative polygon with the fixed
CHIRPS 0.05-degree grid. Calculate intersection areas in an equal-area
projection and store a compact, versioned weight file alongside metadata that
identifies the boundary and grid versions.

For every state/date calculate:

1. Area-weighted mean rainfall (mm)
2. Area-weighted median rainfall (mm)
3. Maximum intersecting grid-cell rainfall (mm)
4. Percentage of valid state area above 1 mm
5. Percentage of valid state area above 10 mm
6. Percentage of valid state area above 20 mm
7. Percentage of valid state area above 50 mm
8. Number of valid intersecting grid cells
9. Valid area percentage

Nodata cells are excluded from both numerator and valid-area denominator.
Results fail validation if valid area falls below a configurable threshold,
defaulting to 95%. Maximum includes any cell with a positive intersection area.

The runtime reads only the raster window covering Malaysia. Final COGs use HTTP
range reads where supported. Preliminary files may be downloaded in full, then
deleted at the end of the run.

## 5. Application structure

Use Python 3.12 with small modules having narrow responsibilities:

- `config.py`: validated environment and command-line configuration
- `catalog.py`: CHIRPS URL construction, availability discovery, and status
- `download.py`: retries, bounded downloads, range-readable raster access
- `boundaries.py`: state-name normalization and boundary validation
- `weights.py`: build/load/validate precomputed spatial weights
- `aggregate.py`: weighted statistics over a raster window
- `records.py`: typed output records and deterministic row locations
- `sheets.py`: tab initialization and batched reads/writes
- `summaries.py`: matrix and monthly summary calculations
- `pipeline.py`: orchestration, replacement rules, and quality events
- `cli.py`: `init-sheet`, `run`, `backfill`, and `build-weights` commands

Avoid GeoPandas, Xarray, SciPy, a web framework, and a database. Use Rasterio,
Shapely, NumPy, Requests, Google Auth, and the Google Sheets API client.

## 6. Google Sheet layout

### `Daily_State_Rainfall`

Columns:

`Date`, `State`, `Type`, `Average_mm`, `Median_mm`, `Maximum_mm`,
`Area_Above_1mm_pct`, `Area_Above_10mm_pct`, `Area_Above_20mm_pct`,
`Area_Above_50mm_pct`, `Valid_Grid_Cells`, `Valid_Area_pct`, `Data_Status`,
`Source_URL`, `Processed_At_UTC`

Rows use a fixed state ordering and deterministic positions: 16 consecutive
rows per date beginning at the configured calendar start, which defaults to
2020-01-01. `init-sheet` creates the date/state skeleton in bounded batches.
Therefore any date/state record can be updated directly without scanning the
sheet, and reruns are idempotent.

The calendar start is configurable only before a Sheet is initialized and is
then immutable for that Sheet because it determines row identities. An optional
pre-2020 archive remains possible by initializing a separate Sheet with
1981-01-01 as its calendar start.

### `State_Daily_Matrix`

One row per date and one average-rainfall column per administrative area.
Rows are deterministic by date.

### `Monthly_Summary`

One row per month/state with total of daily state-average rainfall, average
daily rainfall, rainy days (>=1 mm), heavy-rain days (>=20 mm), maximum daily
state average, valid-day count, and provisional/final status.

### `Data_Quality`

Append-only bounded execution log with run ID, start/end time, requested date
range, dates processed, preliminary/final counts, missing sources, failures,
API request count, and result.

### `Configuration`

Dataset version, boundary version, thresholds, state order, calendar start,
latest attempted date, latest successful preliminary date, latest successful
final date, and sheet schema version.

## 7. Pipeline behavior

### Scheduled run

1. Acquire GitHub Actions concurrency lock.
2. Read the small `Configuration` range.
3. Check a bounded recent window for newly available Preliminary data and Final
   replacements. Do not assume yesterday is published.
4. Process only missing or replaceable dates, capped by configuration.
5. Validate all 16 results for each date before writing.
6. Batch-update daily rows, matrix rows, affected monthly summaries, the
   configuration cells, and one quality-log row.
7. Exit successfully with a `no_new_data` quality event when nothing is ready.

A failure before the Sheets batch update changes no result rows. A partial
write is detected on the next idempotent run and safely repeated.

### Backfill

`backfill --start-date ... --end-date ...` accepts at most 366 days per
invocation by default. GitHub's manual workflow exposes the same inputs.
The normal initial history is run from 2020-01-01 in yearly batches. Dates
before the configured calendar start are rejected.

### Dry run

`--dry-run` performs discovery, download, validation, and calculation but does
not authenticate to or write Google Sheets. Results are printed as compact
JSON/CSV summaries without raster data.

## 8. Error handling and guardrails

- Retry transient HTTP and Google API failures with truncated exponential
  backoff and jitter.
- Treat HTTP 404 as source-not-yet-available, not a pipeline failure.
- Limit individual downloads, total bytes, dates, source-listing pages, Google
  API calls, and wall-clock time per run.
- Reject unexpected redirects away from approved CHC hosts.
- Never log credentials or full service-account JSON.
- Validate spreadsheet ID, expected tab names, schema version, and state order.
- Refuse writes when the remote schema is incompatible.
- Use least-privilege Sheets scope and share only the target spreadsheet with
  the service account.
- Use workflow `timeout-minutes`, least-privilege GitHub permissions, pinned
  major action versions, and no untrusted pull-request execution with secrets.

## 9. Testing and verification

Unit tests cover:

- state-name normalization and 16-area validation
- deterministic row mapping and duplicate prevention
- source preference and Preliminary-to-Final replacement
- missing-date and bounded-window logic
- weighted mean, median, maximum, threshold area, and nodata handling
- monthly summaries
- quota/date/download guardrails
- Google Sheets batch request construction without network calls

Integration tests use generated tiny GeoTIFFs and polygons. They do not download
CHIRPS or contact Google. A separate opt-in smoke test reads one real CHIRPS
date, verifies its metadata, processes Malaysia, and never writes Sheets.

Before handoff, run formatting/static checks, the full offline test suite, the
real-source dry-run smoke test, and inspect the resulting 16 records.

## 10. Documentation and operation

The README will provide exact steps for:

1. Creating the public GitHub repository
2. Creating the Google Sheet
3. Creating a Google Cloud project without enabling billing
4. Enabling the Google Sheets API
5. Creating a service account and key
6. Sharing only the target Sheet with the service-account email
7. Adding `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_SPREADSHEET_ID` secrets
8. Initializing the five tabs
9. Running a dry run
10. Backfilling yearly ranges
11. Enabling and monitoring the daily workflow
12. Rotating or revoking the service-account key
13. Verifying current third-party free-tier terms

## 11. Acceptance criteria

- Offline tests pass on Python 3.12.
- The real-source smoke test returns exactly 16 valid records for one date.
- Repeating a date does not create duplicate rows.
- Preliminary rows are replaced by Final rows without changing row identity.
- A no-data day exits successfully and records the outcome.
- The default Sheet rejects dates before 2020-01-01 without making changes.
- Scheduled execution requires no paid source or recurring AI use.
- No credential or downloaded raster is committed.
- Setup instructions are sufficient for a hobbyist to deploy the project.
