import calendar
from datetime import date

import pytest

from rainfall_tracker.constants import ANALYSIS_ORDER, STATE_ORDER
from rainfall_tracker.dashboard import build_dashboard_snapshot, trailing


def test_trailing_average_and_total():
    values = [1.0, 2.0, 3.0, 4.0]
    assert trailing(values, 3) == [None, None, 2.0, 3.0]
    assert trailing(values, 3, total=True) == [None, None, 6.0, 9.0]
    with pytest.raises(ValueError):
        trailing(values, 0)


def _matrix():
    rows = [["Date", *STATE_ORDER]]
    for offset in range(35):
        day = date(2025, 1, offset + 1) if offset < 31 else date(2025, 2, offset - 30)
        rows.append([day.isoformat(), *[float(offset + index + 1) for index in range(16)]])
    rows.append(["2025-02-05"])
    return rows


def _monthly():
    headers = [
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
    ]
    rows = [headers]
    for year in (2024, 2025):
        for month in (1, 2):
            days = calendar.monthrange(year, month)[1]
            for index, state in enumerate(STATE_ORDER):
                total = float(100 + index + month * 10 + (year - 2024) * 5)
                valid_days = days
                if year == 2025 and month == 2:
                    valid_days = 4
                rows.append(
                    [
                        f"{year}-{month:02d}",
                        state,
                        "State",
                        total,
                        total / valid_days,
                        valid_days,
                        1,
                        30.0,
                        valid_days,
                        "INCOMPLETE" if valid_days != days else "CHIRPS_V3_FINAL_RNL",
                    ]
                )
    return rows


def test_snapshot_uses_latest_populated_date_and_builds_comparisons():
    latest = "2025-02-04"
    detail = [
        [latest, state, "State", 1.0, 1.0, 2.0, 100.0, 20.0, index, 0.0]
        for index, state in enumerate(STATE_ORDER)
    ]
    snapshot = build_dashboard_snapshot(
        _matrix(),
        _monthly(),
        detail,
        state_areas={state: 1.0 for state in STATE_ORDER},
    )

    assert snapshot.latest_date == date(2025, 2, 4)
    assert snapshot.daily_rows[-1][0] == latest
    assert snapshot.daily_rows[-1][1 + 19 + 19] != ""
    assert len(snapshot.ranking_rows) == 19
    johor = next(row for row in snapshot.ranking_rows if row[0] == "Johor")
    assert johor[1] != ""
    assert snapshot.heatmap_headers == ["Area", "2025-01"]
    assert len(snapshot.heatmap_rows) == 19
    assert snapshot.regional_headers[-1] == "Malaysia"
    assert len(snapshot.map_rows) == 16


def test_incomplete_month_is_not_used_for_seasonal_normal():
    snapshot = build_dashboard_snapshot(
        _matrix(),
        _monthly(),
        [],
        state_areas={state: 1.0 for state in STATE_ORDER},
    )
    february_row = next(row for row in snapshot.monthly_rows if row[0] == "2025-02-01")
    johor_normal_index = 1 + len(ANALYSIS_ORDER)
    assert february_row[johor_normal_index] == ""
    assert february_row[-1] is False
