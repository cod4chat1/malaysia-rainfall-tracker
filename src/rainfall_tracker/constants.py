from __future__ import annotations

import os
from datetime import date

CHIRPS_SOURCE_START = date(1981, 1, 1)
DEFAULT_CALENDAR_START = date(2013, 1, 1)
CALENDAR_START = date.fromisoformat(
    os.getenv("RAINFALL_CALENDAR_START", DEFAULT_CALENDAR_START.isoformat())
)
if CALENDAR_START < CHIRPS_SOURCE_START:
    raise ValueError(
        f"RAINFALL_CALENDAR_START cannot predate {CHIRPS_SOURCE_START.isoformat()}"
    )
if (CALENDAR_START.month, CALENDAR_START.day) != (1, 1):
    raise ValueError("RAINFALL_CALENDAR_START must be January 1")
SCHEMA_VERSION = "1"

STATE_ORDER = (
    "Johor",
    "Kedah",
    "Kelantan",
    "Melaka",
    "Negeri Sembilan",
    "Pahang",
    "Penang",
    "Perak",
    "Perlis",
    "Sabah",
    "Sarawak",
    "Selangor",
    "Terengganu",
    "Kuala Lumpur",
    "Putrajaya",
    "Labuan",
)

PENINSULAR_MEMBERS = (
    "Johor",
    "Kedah",
    "Kelantan",
    "Melaka",
    "Negeri Sembilan",
    "Pahang",
    "Penang",
    "Perak",
    "Perlis",
    "Selangor",
    "Terengganu",
    "Kuala Lumpur",
    "Putrajaya",
)
EAST_MALAYSIA_MEMBERS = ("Sabah", "Sarawak", "Labuan")
REGION_MEMBERS = {
    "Peninsular Malaysia": PENINSULAR_MEMBERS,
    "East Malaysia": EAST_MALAYSIA_MEMBERS,
    "Malaysia": STATE_ORDER,
}
REGION_ORDER = tuple(REGION_MEMBERS)
ANALYSIS_ORDER = (*STATE_ORDER, *REGION_ORDER)

FEDERAL_TERRITORIES = frozenset({"Kuala Lumpur", "Putrajaya", "Labuan"})
THRESHOLDS_MM = (1.0, 10.0, 20.0, 50.0)

DAILY_HEADERS = (
    "Date",
    "State",
    "Type",
    "Average_mm",
    "Median_mm",
    "Maximum_mm",
    "Area_Above_1mm_pct",
    "Area_Above_10mm_pct",
    "Area_Above_20mm_pct",
    "Area_Above_50mm_pct",
    "Valid_Grid_Cells",
    "Valid_Area_pct",
    "Data_Status",
    "Source_URL",
    "Processed_At_UTC",
)

MATRIX_HEADERS = ("Date", *STATE_ORDER)

MONTHLY_HEADERS = (
    "Month",
    "State",
    "Type",
    "Total_Rainfall_mm",
    "Average_Daily_Rainfall_mm",
    "Rainy_Days",
    "Heavy_Rain_Days",
    "Maximum_Daily_Rainfall_mm",
    "Valid_Days",
    "Data_Status",
)

QUALITY_HEADERS = (
    "Run_ID",
    "Started_At_UTC",
    "Finished_At_UTC",
    "Requested_Start",
    "Requested_End",
    "Dates_Processed",
    "Preliminary_Dates",
    "Final_Dates",
    "Missing_Dates",
    "Failures",
    "Sheets_Requests",
    "Result",
)

CONFIG_HEADERS = ("Key", "Value")
