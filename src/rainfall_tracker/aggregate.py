from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import THRESHOLDS_MM


@dataclass(frozen=True)
class StateWeights:
    state: str
    flat_indices: np.ndarray
    area_weights: np.ndarray

    def __post_init__(self) -> None:
        if self.flat_indices.ndim != 1 or self.area_weights.ndim != 1:
            raise ValueError("Weight arrays must be one-dimensional")
        if self.flat_indices.size != self.area_weights.size:
            raise ValueError("Weight index and area arrays must have equal length")
        if self.flat_indices.size == 0:
            raise ValueError(f"No grid cells intersect {self.state}")
        if np.any(self.area_weights <= 0):
            raise ValueError("Area weights must be positive")


@dataclass(frozen=True)
class AggregatedState:
    state: str
    average_mm: float
    median_mm: float
    maximum_mm: float
    threshold_percentages: tuple[float, float, float, float]
    valid_grid_cells: int
    valid_area_pct: float


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    sorted_weights = weights[order]
    cutoff = sorted_weights.sum() / 2.0
    index = int(np.searchsorted(np.cumsum(sorted_weights), cutoff, side="left"))
    return float(sorted_values[min(index, sorted_values.size - 1)])


def aggregate_state(
    raster_window: np.ndarray,
    weights: StateWeights,
    *,
    min_valid_area_pct: float = 95.0,
) -> AggregatedState:
    flat = np.asarray(raster_window, dtype=np.float64).reshape(-1)
    values = flat[weights.flat_indices]
    valid = np.isfinite(values) & (values >= 0)
    valid_values = values[valid]
    valid_weights = weights.area_weights[valid].astype(np.float64, copy=False)
    total_area = float(weights.area_weights.sum())
    valid_area = float(valid_weights.sum())
    valid_area_pct = 100.0 * valid_area / total_area
    if valid_values.size == 0 or valid_area_pct < min_valid_area_pct:
        raise ValueError(
            f"{weights.state} valid area {valid_area_pct:.2f}% is below "
            f"{min_valid_area_pct:.2f}%"
        )

    percentages = tuple(
        100.0 * float(valid_weights[valid_values > threshold].sum()) / valid_area
        for threshold in THRESHOLDS_MM
    )
    return AggregatedState(
        state=weights.state,
        average_mm=float(np.average(valid_values, weights=valid_weights)),
        median_mm=weighted_median(valid_values, valid_weights),
        maximum_mm=float(valid_values.max()),
        threshold_percentages=percentages,
        valid_grid_cells=int(valid_values.size),
        valid_area_pct=valid_area_pct,
    )

