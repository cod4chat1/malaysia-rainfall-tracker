from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from .aggregate import aggregate_state
from .catalog import CatalogClient, SourceAsset, should_process
from .config import Settings
from .constants import CALENDAR_START
from .download import DownloadBudget, read_raster_window
from .records import RainfallRecord
from .weights import WeightSet


class StatusReader(Protocol):
    def get_statuses(self, days: list[date]) -> dict[date, str | None]: ...


@dataclass(frozen=True)
class PipelineResult:
    records: tuple[RainfallRecord, ...]
    missing_dates: tuple[date, ...]
    skipped_dates: tuple[date, ...]


def date_range(start: date, end: date) -> list[date]:
    if start < CALENDAR_START:
        raise ValueError(
            f"start date {start.isoformat()} predates this Sheet's calendar start "
            f"{CALENDAR_START.isoformat()}"
        )
    if end < start:
        raise ValueError("end date must not be before start date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def default_date_range(today: date, lookback_days: int) -> list[date]:
    end = today - timedelta(days=1)
    start = end - timedelta(days=lookback_days - 1)
    return date_range(start, end)


def select_assets(
    days: list[date],
    catalog: CatalogClient,
    existing_statuses: dict[date, str | None],
    *,
    max_dates: int,
) -> tuple[list[SourceAsset], list[date], list[date]]:
    selected: list[SourceAsset] = []
    missing: list[date] = []
    skipped: list[date] = []
    for day in days:
        asset = catalog.preferred_asset(day)
        if asset is None:
            missing.append(day)
        elif should_process(existing_statuses.get(day), asset):
            selected.append(asset)
        else:
            skipped.append(day)
    if len(selected) > max_dates:
        skipped.extend(asset.day for asset in selected[max_dates:])
        selected = selected[:max_dates]
    return selected, missing, skipped


def process_assets(
    assets: list[SourceAsset],
    weights: WeightSet,
    settings: Settings,
) -> tuple[RainfallRecord, ...]:
    budget = DownloadBudget(
        per_file_bytes=settings.max_download_bytes,
        total_bytes=settings.max_total_download_bytes,
    )
    records: list[RainfallRecord] = []
    for asset in assets:
        raster = read_raster_window(
            asset.url,
            weights.window,
            budget=budget,
            timeout_seconds=settings.request_timeout_seconds,
        )
        processed_at = datetime.now(UTC)
        daily: list[RainfallRecord] = []
        for state_weights in weights.states:
            result = aggregate_state(
                raster,
                state_weights,
                min_valid_area_pct=settings.min_valid_area_pct,
            )
            t1, t10, t20, t50 = result.threshold_percentages
            daily.append(
                RainfallRecord(
                    day=asset.day,
                    state=result.state,
                    average_mm=result.average_mm,
                    median_mm=result.median_mm,
                    maximum_mm=result.maximum_mm,
                    area_above_1mm_pct=t1,
                    area_above_10mm_pct=t10,
                    area_above_20mm_pct=t20,
                    area_above_50mm_pct=t50,
                    valid_grid_cells=result.valid_grid_cells,
                    valid_area_pct=result.valid_area_pct,
                    data_status=asset.status,
                    source_url=asset.url,
                    processed_at_utc=processed_at,
                )
            )
        if len(daily) != 16:
            raise RuntimeError(f"Expected 16 records for {asset.day}, found {len(daily)}")
        records.extend(daily)
    return tuple(records)
