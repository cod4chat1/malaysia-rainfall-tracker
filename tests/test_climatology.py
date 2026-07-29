from datetime import date, timedelta

import pytest

from rainfall_tracker.climatology import (
    classify_trend,
    consecutive_window,
    expected_month_to_date,
    monthly_normal,
    percentage_difference,
)


def _daily(start: date, count: int, value: float = 1.0):
    return {start + timedelta(days=index): value for index in range(count)}


def test_consecutive_window_rejects_calendar_gaps():
    values = _daily(date(2025, 1, 1), 10)
    assert consecutive_window(values, date(2025, 1, 7), 7) == pytest.approx(1.0)
    assert consecutive_window(
        values, date(2025, 1, 7), 7, total=True
    ) == pytest.approx(7.0)
    values.pop(date(2025, 1, 4))
    assert consecutive_window(values, date(2025, 1, 7), 7) is None


def test_normals_use_only_complete_months_and_same_day_pace():
    values = {}
    values.update(_daily(date(2023, 7, 1), 31, 1.0))
    values.update(_daily(date(2024, 7, 1), 31, 3.0))
    values.update(_daily(date(2025, 7, 1), 10, 100.0))

    assert monthly_normal(
        values, 7, start_year=2023, end_year=2025
    ) == pytest.approx(62.0)
    assert expected_month_to_date(
        values,
        date(2026, 7, 10),
        start_year=2023,
        end_year=2025,
    ) == pytest.approx(20.0)


def test_percentage_and_trend_classification():
    assert percentage_difference(125.0, 100.0) == pytest.approx(0.25)
    assert percentage_difference(10.0, 0.0) is None
    assert classify_trend(0.11) == "Rising"
    assert classify_trend(0.10) == "Stable"
    assert classify_trend(-0.10) == "Stable"
    assert classify_trend(-0.11) == "Falling"
    assert classify_trend(None) == "Insufficient data"
