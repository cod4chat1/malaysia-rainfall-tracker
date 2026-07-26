# Malaysia Rainfall Tracker — Implementation Plan

1. Scaffold a Python 3.12 package with pinned runtime and development
   dependencies.
2. Implement and unit-test state normalization, deterministic Sheet row
   locations, CHIRPS catalog parsing, weighted statistics, replacement rules,
   and monthly summaries.
3. Vendor the pinned Malaysia ADM1 boundary, record attribution, and build a
   versioned CHIRPS-grid weight file.
4. Implement bounded raster access, pipeline orchestration, Google Sheets
   initialization and batched updates, and the command-line interface.
5. Add cost-guarded GitHub Actions workflows for daily updates, manual yearly
   backfills, tests, and low-frequency dependency proposals.
6. Document setup, secrets, dry runs, backfill, normal operation, and key
   rotation.
7. Run the complete offline test suite and a no-write smoke test against one
   real CHIRPS date.

