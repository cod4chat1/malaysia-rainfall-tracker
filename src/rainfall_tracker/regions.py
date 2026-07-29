from __future__ import annotations

from pathlib import Path

from .constants import REGION_MEMBERS, STATE_ORDER
from .weights import load_weights


def load_state_effective_areas(path: Path) -> dict[str, float]:
    weights = load_weights(path)
    areas = {
        state.state: float(state.area_weights.sum())
        for state in weights.states
    }
    if tuple(areas) != STATE_ORDER:
        raise ValueError("Spatial weights do not contain the canonical state order")
    if any(area <= 0 for area in areas.values()):
        raise ValueError("Every state must have a positive effective area")
    return areas


def derive_regional_values(
    state_values: dict[str, float],
    state_areas: dict[str, float],
) -> dict[str, float]:
    missing_areas = [state for state in STATE_ORDER if state not in state_areas]
    if missing_areas:
        raise ValueError(
            "Missing effective areas: " + ", ".join(missing_areas)
        )

    result: dict[str, float] = {}
    for region, members in REGION_MEMBERS.items():
        if any(state not in state_values for state in members):
            continue
        denominator = sum(state_areas[state] for state in members)
        if denominator <= 0:
            raise ValueError(f"{region} has no positive effective area")
        numerator = sum(
            float(state_values[state]) * state_areas[state]
            for state in members
        )
        result[region] = numerator / denominator
    return result
