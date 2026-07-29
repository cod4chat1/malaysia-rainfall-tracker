from __future__ import annotations

import calendar
from datetime import date, timedelta
from statistics import mean

TREND_THRESHOLD = 0.10


def consecutive_window(
    values: dict[date, float],
    day: date,
    window: int,
    *,
    total: bool = False,
) -> float | None:
    if window <= 0:
        raise ValueError("Moving window must be positive")
    start = day - timedelta(days=window - 1)
    window_values: list[float] = []
    current = start
    while current <= day:
        value = values.get(current)
        if value is None:
            return None
        window_values.append(float(value))
        current += timedelta(days=1)
    return sum(window_values) if total else mean(window_values)


def complete_month_total(
    values: dict[date, float],
    year: int,
    month: int,
) -> float | None:
    day_count = calendar.monthrange(year, month)[1]
    monthly = [
        values.get(date(year, month, day))
        for day in range(1, day_count + 1)
    ]
    if any(value is None for value in monthly):
        return None
    return sum(float(value) for value in monthly if value is not None)


def month_to_date_total(
    values: dict[date, float],
    through: date,
) -> float | None:
    monthly = [
        values.get(date(through.year, through.month, day))
        for day in range(1, through.day + 1)
    ]
    if any(value is None for value in monthly):
        return None
    return sum(float(value) for value in monthly if value is not None)


def monthly_normal(
    values: dict[date, float],
    month: int,
    *,
    start_year: int,
    end_year: int,
) -> float | None:
    totals = [
        total
        for year in range(start_year, end_year + 1)
        if (total := complete_month_total(values, year, month)) is not None
    ]
    return mean(totals) if totals else None


def expected_month_to_date(
    values: dict[date, float],
    through: date,
    *,
    start_year: int,
    end_year: int,
) -> float | None:
    totals: list[float] = []
    for year in range(start_year, end_year + 1):
        if through.day > calendar.monthrange(year, through.month)[1]:
            continue
        if complete_month_total(values, year, through.month) is None:
            continue
        historical_day = date(year, through.month, through.day)
        total = month_to_date_total(values, historical_day)
        if total is not None:
            totals.append(total)
    return mean(totals) if totals else None


def percentage_difference(actual: float | None, baseline: float | None) -> float | None:
    if actual is None or baseline in (None, 0):
        return None
    return actual / baseline - 1


def classify_trend(value: float | None) -> str:
    if value is None:
        return "Insufficient data"
    if value > TREND_THRESHOLD:
        return "Rising"
    if value < -TREND_THRESHOLD:
        return "Falling"
    return "Stable"
