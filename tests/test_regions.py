from pathlib import Path

import pytest

from rainfall_tracker.constants import (
    ANALYSIS_ORDER,
    EAST_MALAYSIA_MEMBERS,
    PENINSULAR_MEMBERS,
    STATE_ORDER,
)
from rainfall_tracker.regions import derive_regional_values, load_state_effective_areas


def test_regional_membership_and_analysis_order():
    assert set(PENINSULAR_MEMBERS).isdisjoint(EAST_MALAYSIA_MEMBERS)
    assert set(PENINSULAR_MEMBERS) | set(EAST_MALAYSIA_MEMBERS) == set(STATE_ORDER)
    assert ANALYSIS_ORDER[-3:] == (
        "Peninsular Malaysia",
        "East Malaysia",
        "Malaysia",
    )


def test_regional_values_are_area_weighted_and_require_complete_members():
    state_areas = {state: 1.0 for state in STATE_ORDER}
    state_areas["Johor"] = 3.0
    values = {state: 10.0 for state in STATE_ORDER}
    values["Johor"] = 30.0

    regional = derive_regional_values(values, state_areas)

    expected_peninsular = (30.0 * 3.0 + 12 * 10.0) / 15.0
    assert regional["Peninsular Malaysia"] == pytest.approx(expected_peninsular)
    assert regional["East Malaysia"] == pytest.approx(10.0)
    expected_malaysia = (30.0 * 3.0 + 15 * 10.0) / 18.0
    assert regional["Malaysia"] == pytest.approx(expected_malaysia)

    values.pop("Sabah")
    incomplete = derive_regional_values(values, state_areas)
    assert "Peninsular Malaysia" in incomplete
    assert "East Malaysia" not in incomplete
    assert "Malaysia" not in incomplete


def test_load_effective_areas_from_vendored_weights():
    areas = load_state_effective_areas(
        Path("data/chirps_v3_malaysia_weights.npz")
    )
    assert tuple(areas) == STATE_ORDER
    assert all(value > 0 for value in areas.values())
