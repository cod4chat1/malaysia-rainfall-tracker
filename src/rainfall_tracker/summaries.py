from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from .constants import FEDERAL_TERRITORIES
from .records import RainfallRecord


@dataclass(frozen=True)
class MonthlySummary:
    month: date
    state: str
    total_rainfall_mm: float
    average_daily_rainfall_mm: float
    rainy_days: int
    heavy_rain_days: int
    maximum_daily_rainfall_mm: float
    valid_days: int
    data_status: str

    def sheet_values(self) -> list[object]:
        area_type = "Federal Territory" if self.state in FEDERAL_TERRITORIES else "State"
        return [
            self.month.strftime("%Y-%m"),
            self.state,
            area_type,
            round(self.total_rainfall_mm, 3),
            round(self.average_daily_rainfall_mm, 3),
            self.rainy_days,
            self.heavy_rain_days,
            round(self.maximum_daily_rainfall_mm, 3),
            self.valid_days,
            self.data_status,
        ]


def summarize_month(records: list[RainfallRecord]) -> MonthlySummary:
    if not records:
        raise ValueError("Cannot summarize an empty record list")
    state = records[0].state
    month = records[0].day.replace(day=1)
    if any(record.state != state or record.day.replace(day=1) != month for record in records):
        raise ValueError("Monthly records must have the same state and month")
    values = [record.average_mm for record in records]
    all_final = all(record.data_status == "CHIRPS_V3_FINAL_RNL" for record in records)
    expected_days = calendar.monthrange(month.year, month.month)[1]
    if len(records) == expected_days and all_final:
        status = "CHIRPS_V3_FINAL_RNL"
    elif not all_final:
        status = "PROVISIONAL"
    else:
        status = "INCOMPLETE"
    return MonthlySummary(
        month=month,
        state=state,
        total_rainfall_mm=sum(values),
        average_daily_rainfall_mm=sum(values) / len(values),
        rainy_days=sum(value >= 1.0 for value in values),
        heavy_rain_days=sum(value >= 20.0 for value in values),
        maximum_daily_rainfall_mm=max(values),
        valid_days=len(values),
        data_status=status,
    )
