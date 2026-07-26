from datetime import UTC, date, datetime

import pytest

from rainfall_tracker.records import RainfallRecord
from rainfall_tracker.summaries import summarize_month


def record(day, value, status="CHIRPS_V3_FINAL_RNL"):
    return RainfallRecord(
        day=day,
        state="Johor",
        average_mm=value,
        median_mm=value,
        maximum_mm=value,
        area_above_1mm_pct=100.0,
        area_above_10mm_pct=0.0,
        area_above_20mm_pct=0.0,
        area_above_50mm_pct=0.0,
        valid_grid_cells=10,
        valid_area_pct=100.0,
        data_status=status,
        source_url="https://data.chc.ucsb.edu/example.tif",
        processed_at_utc=datetime(2025, 1, 5, tzinfo=UTC),
    )


def test_monthly_summary():
    summary = summarize_month(
        [
            record(date(2025, 1, 1), 0.5),
            record(date(2025, 1, 2), 2.0),
            record(date(2025, 1, 3), 25.0, "CHIRPS_V3_PRELIM_SAT"),
        ]
    )
    assert summary.total_rainfall_mm == pytest.approx(27.5)
    assert summary.average_daily_rainfall_mm == pytest.approx(27.5 / 3)
    assert summary.rainy_days == 2
    assert summary.heavy_rain_days == 1
    assert summary.maximum_daily_rainfall_mm == 25.0
    assert summary.data_status == "PROVISIONAL"


def test_monthly_summary_rejects_mixed_states_or_months():
    values = [record(date(2025, 1, 1), 1.0), record(date(2025, 2, 1), 2.0)]
    with pytest.raises(ValueError):
        summarize_month(values)


def test_partial_all_final_month_is_incomplete():
    summary = summarize_month([record(date(2025, 1, 1), 1.0)])
    assert summary.data_status == "INCOMPLETE"
