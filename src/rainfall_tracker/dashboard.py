from __future__ import annotations

import calendar
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from statistics import mean

from .constants import STATE_ORDER


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


def trailing(values: list[float], window: int, *, total: bool = False) -> list[float | None]:
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


def _daily_table(
    matrix_values: list[list[object]],
) -> tuple[list[str], list[list[object]], dict[str, list[tuple[date, float]]]]:
    if not matrix_values:
        raise ValueError("State daily matrix is empty")
    header = [str(value) for value in matrix_values[0]]
    indexes = {state: header.index(state) for state in STATE_ORDER}
    observations: dict[str, list[tuple[date, float]]] = defaultdict(list)
    by_day: dict[date, dict[str, float]] = {}
    for row in matrix_values[1:]:
        if not row or not row[0]:
            continue
        try:
            day = date.fromisoformat(str(row[0])[:10])
        except ValueError:
            continue
        values: dict[str, float] = {}
        for state in STATE_ORDER:
            value = _number(row, indexes[state])
            if value is not None:
                values[state] = value
                observations[state].append((day, value))
        if values:
            by_day[day] = values
    if not by_day:
        raise ValueError("State daily matrix has no rainfall observations")

    calculations: dict[str, dict[date, tuple[float | None, float | None, float | None]]] = {}
    for state in STATE_ORDER:
        state_observations = observations[state]
        dates = [item[0] for item in state_observations]
        values = [item[1] for item in state_observations]
        ma7 = trailing(values, 7)
        ma30 = trailing(values, 30)
        roll30 = trailing(values, 30, total=True)
        calculations[state] = {
            day: (ma7_value, ma30_value, roll30_value)
            for day, ma7_value, ma30_value, roll30_value in zip(
                dates, ma7, ma30, roll30, strict=True
            )
        }

    headers = [
        "Date",
        *STATE_ORDER,
        *[f"{state} MA7" for state in STATE_ORDER],
        *[f"{state} MA30" for state in STATE_ORDER],
        *[f"{state} Rolling30" for state in STATE_ORDER],
    ]
    rows: list[list[object]] = []
    for day in sorted(by_day):
        actual = [by_day[day].get(state, "") for state in STATE_ORDER]
        ma7_values = [
            (
                calculations[state].get(day, (None, None, None))[0]
                if calculations[state].get(day, (None, None, None))[0] is not None
                else ""
            )
            for state in STATE_ORDER
        ]
        ma30_values = [
            (
                calculations[state].get(day, (None, None, None))[1]
                if calculations[state].get(day, (None, None, None))[1] is not None
                else ""
            )
            for state in STATE_ORDER
        ]
        roll30_values = [
            (
                calculations[state].get(day, (None, None, None))[2]
                if calculations[state].get(day, (None, None, None))[2] is not None
                else ""
            )
            for state in STATE_ORDER
        ]
        rows.append(
            [
                day.isoformat(),
                *[round(value, 3) if value != "" else "" for value in actual],
                *[round(value, 3) if value != "" else "" for value in ma7_values],
                *[round(value, 3) if value != "" else "" for value in ma30_values],
                *[round(value, 3) if value != "" else "" for value in roll30_values],
            ]
        )
    return headers, rows, observations


def _monthly_table(
    monthly_values: list[list[object]],
) -> tuple[
    list[str],
    list[list[object]],
    dict[tuple[date, str], dict[str, object]],
    dict[tuple[str, int], float],
]:
    if not monthly_values:
        raise ValueError("Monthly summary is empty")
    header = [str(value) for value in monthly_values[0]]
    column = {name: header.index(name) for name in header}
    summaries: dict[tuple[date, str], dict[str, object]] = {}
    normals_source: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in monthly_values[1:]:
        if len(row) <= column["Total_Rainfall_mm"] or not row[column["Total_Rainfall_mm"]]:
            continue
        month = date.fromisoformat(f"{str(row[column['Month']])[:7]}-01")
        state = str(row[column["State"]])
        total = float(row[column["Total_Rainfall_mm"]])
        valid_days = int(float(row[column["Valid_Days"]]))
        complete = valid_days == calendar.monthrange(month.year, month.month)[1]
        item = {
            "total": total,
            "valid_days": valid_days,
            "complete": complete,
            "rainy_days": int(float(row[column["Rainy_Days"]])),
            "heavy_days": int(float(row[column["Heavy_Rain_Days"]])),
            "maximum": float(row[column["Maximum_Daily_Rainfall_mm"]]),
        }
        summaries[(month, state)] = item
        if complete:
            normals_source[(state, month.month)].append(total)
    normals = {key: mean(values) for key, values in normals_source.items() if values}

    months = sorted({month for month, _state in summaries})
    headers = [
        "Month",
        *[f"{state} Total" for state in STATE_ORDER],
        *[f"{state} Normal" for state in STATE_ORDER],
        "Complete",
    ]
    rows: list[list[object]] = []
    for month in months:
        totals = [
            round(float(summaries[(month, state)]["total"]), 3)
            if (month, state) in summaries
            else ""
            for state in STATE_ORDER
        ]
        month_normals = [
            round(normals[(state, month.month)], 3)
            if (state, month.month) in normals
            else ""
            for state in STATE_ORDER
        ]
        complete = all(
            bool(summaries.get((month, state), {}).get("complete"))
            for state in STATE_ORDER
        )
        rows.append([month.isoformat(), *totals, *month_normals, complete])
    return headers, rows, summaries, normals


def build_dashboard_snapshot(
    matrix_values: list[list[object]],
    monthly_values: list[list[object]],
    detail_values: list[list[object]],
) -> DashboardSnapshot:
    daily_headers, daily_rows, observations = _daily_table(matrix_values)
    monthly_headers, monthly_rows, summaries, normals = _monthly_table(monthly_values)
    latest_date = max(day for rows in observations.values() for day, _value in rows)
    latest_month = latest_date.replace(day=1)

    latest_area20: dict[str, float] = {}
    for row in detail_values:
        if len(row) <= 8 or not row[3] or str(row[0])[:10] != latest_date.isoformat():
            continue
        latest_area20[str(row[1])] = float(row[8])

    ranking_headers = [
        "State",
        "30-day rainfall mm",
        "Vs seasonal normal",
        "Rainy days",
        "Heavy-rain days",
        "Maximum daily mm",
        "Latest area >20mm %",
    ]
    ranking_rows: list[list[object]] = []
    for state in STATE_ORDER:
        recent = [value for day, value in observations[state] if day <= latest_date][-30:]
        rolling = sum(recent) if recent else 0.0
        normal = normals.get((state, latest_month.month))
        difference = rolling / normal - 1 if normal else None
        ranking_rows.append(
            [
                state,
                round(rolling, 3),
                round(difference, 4) if difference is not None else "",
                sum(value >= 1.0 for value in recent),
                sum(value >= 20.0 for value in recent),
                round(max(recent), 3) if recent else "",
                round(latest_area20[state], 3) if state in latest_area20 else "",
            ]
        )
    ranking_rows.sort(key=lambda row: float(row[1]), reverse=True)

    complete_months = sorted(
        {
            month
            for month, _state in summaries
            if all(
                bool(summaries.get((month, state), {}).get("complete"))
                for state in STATE_ORDER
            )
        }
    )[-12:]
    heatmap_headers = ["State", *[month.strftime("%Y-%m") for month in complete_months]]
    heatmap_rows = [
        [
            state,
            *[
                round(float(summaries[(month, state)]["total"]), 3)
                for month in complete_months
            ],
        ]
        for state in STATE_ORDER
    ]

    return DashboardSnapshot(
        latest_date=latest_date,
        daily_headers=daily_headers,
        daily_rows=daily_rows,
        monthly_headers=monthly_headers,
        monthly_rows=monthly_rows,
        ranking_headers=ranking_headers,
        ranking_rows=ranking_rows,
        heatmap_headers=heatmap_headers,
        heatmap_rows=heatmap_rows,
    )
