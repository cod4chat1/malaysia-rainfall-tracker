from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date
from statistics import mean

from .climatology import (
    classify_trend,
    complete_month_total,
    consecutive_window,
    expected_month_to_date,
    month_to_date_total,
    monthly_normal,
    percentage_difference,
)
from .constants import ANALYSIS_ORDER, REGION_ORDER, STATE_ORDER
from .regions import derive_regional_values

BASELINE_START_YEAR = 2013


@dataclass(frozen=True)
class DashboardSnapshot:
    latest_date: date
    daily_headers: list[str]
    daily_rows: list[list[object]]
    monthly_headers: list[str]
    monthly_rows: list[list[object]]
    ranking_headers: list[str]
    ranking_rows: list[list[object]]
    heatmap_headers: list[str]
    heatmap_rows: list[list[object]]
    baseline_start_year: int = BASELINE_START_YEAR
    baseline_end_year: int = BASELINE_START_YEAR
    regional_headers: list[str] = field(default_factory=list)
    regional_rows: list[list[object]] = field(default_factory=list)
    map_headers: list[str] = field(default_factory=list)
    map_rows: list[list[object]] = field(default_factory=list)


def trailing(values: list[float], window: int, *, total: bool = False) -> list[float | None]:
    """Retained for callers that need a dense-series moving calculation."""
    if window <= 0:
        raise ValueError("Moving window must be positive")
    result: list[float | None] = []
    recent: deque[float] = deque(maxlen=window)
    for value in values:
        recent.append(float(value))
        if len(recent) < window:
            result.append(None)
        elif total:
            result.append(sum(recent))
        else:
            result.append(mean(recent))
    return result


def _number(row: list[object], index: int) -> float | None:
    if index >= len(row) or row[index] in ("", None):
        return None
    try:
        return float(row[index])
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 3) -> float | str:
    return round(value, digits) if value is not None else ""


def _observations(
    matrix_values: list[list[object]],
    state_areas: dict[str, float],
) -> tuple[dict[date, dict[str, float]], dict[str, dict[date, float]]]:
    if not matrix_values:
        raise ValueError("State daily matrix is empty")
    header = [str(value) for value in matrix_values[0]]
    missing = [state for state in STATE_ORDER if state not in header]
    if missing:
        raise ValueError("State daily matrix is missing: " + ", ".join(missing))
    indexes = {state: header.index(state) for state in STATE_ORDER}
    by_day: dict[date, dict[str, float]] = {}
    by_area: dict[str, dict[date, float]] = {area: {} for area in ANALYSIS_ORDER}

    for row in matrix_values[1:]:
        if not row or not row[0]:
            continue
        try:
            day = date.fromisoformat(str(row[0])[:10])
        except ValueError:
            continue
        values = {
            state: value
            for state in STATE_ORDER
            if (value := _number(row, indexes[state])) is not None
        }
        values.update(derive_regional_values(values, state_areas))
        if not values:
            continue
        by_day[day] = values
        for area, value in values.items():
            by_area[area][day] = value

    if not by_day:
        raise ValueError("State daily matrix has no rainfall observations")
    return by_day, by_area


def _daily_table(
    by_day: dict[date, dict[str, float]],
    by_area: dict[str, dict[date, float]],
) -> tuple[list[str], list[list[object]]]:
    headers = [
        "Date",
        *ANALYSIS_ORDER,
        *[f"{area} MA7" for area in ANALYSIS_ORDER],
        *[f"{area} MA30" for area in ANALYSIS_ORDER],
        *[f"{area} Rolling30" for area in ANALYSIS_ORDER],
    ]
    rows: list[list[object]] = []
    for day in sorted(by_day):
        rows.append(
            [
                day.isoformat(),
                *[_round(by_day[day].get(area)) for area in ANALYSIS_ORDER],
                *[
                    _round(consecutive_window(by_area[area], day, 7))
                    for area in ANALYSIS_ORDER
                ],
                *[
                    _round(consecutive_window(by_area[area], day, 30))
                    for area in ANALYSIS_ORDER
                ],
                *[
                    _round(consecutive_window(by_area[area], day, 30, total=True))
                    for area in ANALYSIS_ORDER
                ],
            ]
        )
    return headers, rows


def _month_range(by_day: dict[date, dict[str, float]]) -> list[date]:
    first = min(by_day).replace(day=1)
    last = max(by_day).replace(day=1)
    months: list[date] = []
    current = first
    while current <= last:
        months.append(current)
        current = (
            date(current.year + 1, 1, 1)
            if current.month == 12
            else date(current.year, current.month + 1, 1)
        )
    return months


def _monthly_table(
    by_day: dict[date, dict[str, float]],
    by_area: dict[str, dict[date, float]],
    *,
    baseline_start_year: int,
    baseline_end_year: int,
) -> tuple[list[str], list[list[object]], dict[tuple[date, str], float | None]]:
    months = _month_range(by_day)
    totals = {
        (month, area): complete_month_total(by_area[area], month.year, month.month)
        for month in months
        for area in ANALYSIS_ORDER
    }
    normals = {
        (area, month): monthly_normal(
            by_area[area],
            month,
            start_year=baseline_start_year,
            end_year=baseline_end_year,
        )
        for area in ANALYSIS_ORDER
        for month in range(1, 13)
    }
    headers = [
        "Month",
        *[f"{area} Total" for area in ANALYSIS_ORDER],
        *[f"{area} Normal" for area in ANALYSIS_ORDER],
        "Complete",
    ]
    rows = [
        [
            month.isoformat(),
            *[_round(totals[(month, area)]) for area in ANALYSIS_ORDER],
            *[_round(normals[(area, month.month)]) for area in ANALYSIS_ORDER],
            all(totals[(month, area)] is not None for area in ANALYSIS_ORDER),
        ]
        for month in months
    ]
    return headers, rows, totals


def _current_conditions(
    by_area: dict[str, dict[date, float]],
    latest_date: date,
    *,
    baseline_start_year: int,
    baseline_end_year: int,
) -> tuple[list[str], list[list[object]]]:
    headers = [
        "Area",
        "MTD rainfall mm",
        "Expected MTD mm",
        "MTD anomaly",
        "7-day average mm",
        "30-day average mm",
        "Recent trend",
        "Trend %",
    ]
    rows: list[list[object]] = []
    for area in ANALYSIS_ORDER:
        values = by_area[area]
        mtd = month_to_date_total(values, latest_date)
        expected = expected_month_to_date(
            values,
            latest_date,
            start_year=baseline_start_year,
            end_year=baseline_end_year,
        )
        anomaly = percentage_difference(mtd, expected)
        ma7 = consecutive_window(values, latest_date, 7)
        ma30 = consecutive_window(values, latest_date, 30)
        trend = percentage_difference(ma7, ma30)
        rows.append(
            [
                area,
                _round(mtd),
                _round(expected),
                _round(anomaly, 4),
                _round(ma7),
                _round(ma30),
                classify_trend(trend),
                _round(trend, 4),
            ]
        )
    return headers, rows


def _heatmap(
    totals: dict[tuple[date, str], float | None],
) -> tuple[list[str], list[list[object]]]:
    complete_months = sorted(
        {
            month
            for month, _area in totals
            if all(totals.get((month, area)) is not None for area in ANALYSIS_ORDER)
        }
    )[-12:]
    headers = ["Area", *[month.strftime("%Y-%m") for month in complete_months]]
    rows = [
        [
            area,
            *[_round(totals[(month, area)]) for month in complete_months],
        ]
        for area in ANALYSIS_ORDER
    ]
    return headers, rows


def build_dashboard_snapshot(
    matrix_values: list[list[object]],
    monthly_values: list[list[object]],
    detail_values: list[list[object]],
    *,
    state_areas: dict[str, float],
    baseline_start_year: int = BASELINE_START_YEAR,
) -> DashboardSnapshot:
    # Monthly and detailed source tabs remain canonical outputs, but dashboard
    # analytics are derived from one daily series so states and regions use the
    # same completeness and climatology rules.
    del monthly_values, detail_values
    by_day, by_area = _observations(matrix_values, state_areas)
    complete_days = [
        day for day, values in by_day.items() if all(state in values for state in STATE_ORDER)
    ]
    if not complete_days:
        raise ValueError("No date contains all 16 Malaysian administrative areas")
    latest_date = max(complete_days)
    baseline_end_year = latest_date.year - 1
    if baseline_end_year < baseline_start_year:
        raise ValueError("Not enough history to establish a seasonal baseline")

    daily_headers, daily_rows = _daily_table(by_day, by_area)
    monthly_headers, monthly_rows, totals = _monthly_table(
        by_day,
        by_area,
        baseline_start_year=baseline_start_year,
        baseline_end_year=baseline_end_year,
    )
    ranking_headers, ranking_rows = _current_conditions(
        by_area,
        latest_date,
        baseline_start_year=baseline_start_year,
        baseline_end_year=baseline_end_year,
    )
    heatmap_headers, heatmap_rows = _heatmap(totals)
    map_rows = [
        [row[0], latest_date.isoformat(), *row[1:]]
        for row in ranking_rows
        if row[0] in STATE_ORDER
    ]
    regional_rows = [
        [day.isoformat(), *[_round(by_day[day].get(region)) for region in REGION_ORDER]]
        for day in sorted(by_day)
    ]

    return DashboardSnapshot(
        latest_date=latest_date,
        baseline_start_year=baseline_start_year,
        baseline_end_year=baseline_end_year,
        daily_headers=daily_headers,
        daily_rows=daily_rows,
        monthly_headers=monthly_headers,
        monthly_rows=monthly_rows,
        ranking_headers=ranking_headers,
        ranking_rows=ranking_rows,
        heatmap_headers=heatmap_headers,
        heatmap_rows=heatmap_rows,
        regional_headers=["Date", *REGION_ORDER],
        regional_rows=regional_rows,
        map_headers=["State", "Latest date", *ranking_headers[1:]],
        map_rows=map_rows,
    )
