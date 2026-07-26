import numpy as np
import pytest

from rainfall_tracker.aggregate import StateWeights, aggregate_state, weighted_median


def test_weighted_median_uses_area_weights():
    values = np.array([1.0, 5.0, 10.0])
    weights = np.array([1.0, 8.0, 1.0])
    assert weighted_median(values, weights) == 5.0


def test_aggregate_state_uses_valid_area_for_thresholds():
    raster = np.array([[0.0, 5.0], [25.0, np.nan]])
    weights = StateWeights(
        state="Johor",
        flat_indices=np.array([0, 1, 2, 3]),
        area_weights=np.array([1.0, 2.0, 1.0, 1.0]),
    )
    result = aggregate_state(raster, weights, min_valid_area_pct=70.0)
    assert result.average_mm == pytest.approx(8.75)
    assert result.median_mm == 5.0
    assert result.maximum_mm == 25.0
    assert result.threshold_percentages == pytest.approx((75.0, 25.0, 25.0, 0.0))
    assert result.valid_grid_cells == 3
    assert result.valid_area_pct == pytest.approx(80.0)


def test_aggregate_state_rejects_low_valid_area():
    raster = np.array([[np.nan, 5.0]])
    weights = StateWeights(
        state="Johor",
        flat_indices=np.array([0, 1]),
        area_weights=np.array([9.0, 1.0]),
    )
    with pytest.raises(ValueError, match="valid area"):
        aggregate_state(raster, weights, min_valid_area_pct=95.0)

