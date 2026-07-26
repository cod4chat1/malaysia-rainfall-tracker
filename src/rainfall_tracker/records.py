from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .constants import CALENDAR_START, FEDERAL_TERRITORIES, STATE_ORDER


def daily_row(day: date, state: str) -> int:
    if day < CALENDAR_START:
        raise ValueError(f"Date cannot be before {CALENDAR_START.isoformat()}")
    try:
        state_index = STATE_ORDER.index(state)
    except ValueError as exc:
        raise ValueError(f"Unknown state: {state}") from exc
    return 2 + (day - CALENDAR_START).days * len(STATE_ORDER) + state_index


def matrix_row(day: date) -> int:
    if day < CALENDAR_START:
        raise ValueError(f"Date cannot be before {CALENDAR_START.isoformat()}")
    return 2 + (day - CALENDAR_START).days


def monthly_row(month: date, state: str) -> int:
    if month.day != 1:
        raise ValueError("Monthly row date must be the first of the month")
    months = (month.year - CALENDAR_START.year) * 12 + month.month - CALENDAR_START.month
    if months < 0:
        raise ValueError(f"Month cannot be before {CALENDAR_START.isoformat()}")
    try:
        state_index = STATE_ORDER.index(state)
    except ValueError as exc:
        raise ValueError(f"Unknown state: {state}") from exc
    return 2 + months * len(STATE_ORDER) + state_index


@dataclass(frozen=True)
class RainfallRecord:
    day: date
    state: str
    average_mm: float
    median_mm: float
    maximum_mm: float
    area_above_1mm_pct: float
    area_above_10mm_pct: float
    area_above_20mm_pct: float
    area_above_50mm_pct: float
    valid_grid_cells: int
    valid_area_pct: float
    data_status: str
    source_url: str
    processed_at_utc: datetime

    @property
    def area_type(self) -> str:
        return "Federal Territory" if self.state in FEDERAL_TERRITORIES else "State"

    def sheet_values(self) -> list[object]:
        return [
            self.day.isoformat(),
            self.state,
            self.area_type,
            round(self.average_mm, 3),
            round(self.median_mm, 3),
            round(self.maximum_mm, 3),
            round(self.area_above_1mm_pct, 3),
            round(self.area_above_10mm_pct, 3),
            round(self.area_above_20mm_pct, 3),
            round(self.area_above_50mm_pct, 3),
            self.valid_grid_cells,
            round(self.valid_area_pct, 3),
            self.data_status,
            self.source_url,
            self.processed_at_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        ]

