from __future__ import annotations

from datetime import date

CALENDAR_START = date(1981, 1, 1)
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

