# Daily update operations

The Google Sheet is updated by `.github/workflows/daily-rainfall.yml` at 00:30 UTC (08:30 Malaysia time). The scheduled workflow runs from the default `master` branch.

## Public repository inactivity

GitHub can automatically disable scheduled workflows after 60 days without repository activity. Scheduled workflow runs and sheet writes should not be treated as repository edits. Review the last commit date before the 60-day mark and make a useful maintenance change if needed. Check the Actions tab to confirm the Daily rainfall update workflow remains enabled.

## After an interruption

1. Open the Actions tab and enable the Daily rainfall update workflow if GitHub disabled it.
2. Run it manually with `mode: recent`; review its log and the Google Sheet's latest available dates.
3. If more dates are missing than the recent mode can cover, use the existing backfill workflow for the missing date range in manageable batches.
4. Confirm the Daily_State_Rainfall, State_Daily_Matrix, Monthly_Summary, and Data_Quality sheets reflect the recovered dates.

Keep the service account secret and spreadsheet ID in GitHub Actions secrets. Do not commit credentials to this repository.
