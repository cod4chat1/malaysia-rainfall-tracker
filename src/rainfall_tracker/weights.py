from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.windows import Window
from shapely.geometry import box
from shapely.ops import transform
from shapely.prepared import prep

from .aggregate import StateWeights
from .boundaries import load_boundaries
from .constants import STATE_ORDER

GRID_WEST = -180.0
GRID_NORTH = 60.0
GRID_RESOLUTION = 0.05
GRID_WIDTH = 7200
GRID_HEIGHT = 2400
WEIGHT_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class WeightSet:
    window: Window
    states: tuple[StateWeights, ...]
    boundary_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _window_for_bounds(bounds: tuple[float, float, float, float]) -> Window:
    min_x, min_y, max_x, max_y = bounds
    col_start = max(0, math.floor((min_x - GRID_WEST) / GRID_RESOLUTION))
    col_stop = min(GRID_WIDTH, math.ceil((max_x - GRID_WEST) / GRID_RESOLUTION))
    row_start = max(0, math.floor((GRID_NORTH - max_y) / GRID_RESOLUTION))
    row_stop = min(GRID_HEIGHT, math.ceil((GRID_NORTH - min_y) / GRID_RESOLUTION))
    return Window(
        col_off=col_start,
        row_off=row_start,
        width=col_stop - col_start,
        height=row_stop - row_start,
    )


def _cell_geometry(global_row: int, global_col: int):
    left = GRID_WEST + global_col * GRID_RESOLUTION
    top = GRID_NORTH - global_row * GRID_RESOLUTION
    return box(left, top - GRID_RESOLUTION, left + GRID_RESOLUTION, top)


def build_weights(boundary_path: Path, output_path: Path) -> WeightSet:
    boundaries = load_boundaries(boundary_path)
    country_bounds = (
        min(geometry.bounds[0] for geometry in boundaries.values()),
        min(geometry.bounds[1] for geometry in boundaries.values()),
        max(geometry.bounds[2] for geometry in boundaries.values()),
        max(geometry.bounds[3] for geometry in boundaries.values()),
    )
    window = _window_for_bounds(country_bounds)
    equal_area = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform
    states: list[StateWeights] = []

    for state in STATE_ORDER:
        geometry = boundaries[state]
        prepared = prep(geometry)
        candidate = _window_for_bounds(geometry.bounds)
        indices: list[int] = []
        areas: list[float] = []
        row_end = int(candidate.row_off + candidate.height)
        col_end = int(candidate.col_off + candidate.width)
        for global_row in range(int(candidate.row_off), row_end):
            for global_col in range(int(candidate.col_off), col_end):
                cell = _cell_geometry(global_row, global_col)
                if not prepared.intersects(cell):
                    continue
                intersection = geometry.intersection(cell)
                if intersection.is_empty:
                    continue
                area = float(transform(equal_area, intersection).area)
                if area <= 0:
                    continue
                local_row = global_row - int(window.row_off)
                local_col = global_col - int(window.col_off)
                flat_index = local_row * int(window.width) + local_col
                indices.append(flat_index)
                areas.append(area)
        states.append(
            StateWeights(
                state=state,
                flat_indices=np.asarray(indices, dtype=np.int32),
                area_weights=np.asarray(areas, dtype=np.float64),
            )
        )

    metadata = {
        "schema_version": WEIGHT_SCHEMA_VERSION,
        "boundary_sha256": _sha256(boundary_path),
        "grid": {
            "west": GRID_WEST,
            "north": GRID_NORTH,
            "resolution": GRID_RESOLUTION,
            "width": GRID_WIDTH,
            "height": GRID_HEIGHT,
        },
        "window": {
            "col_off": int(window.col_off),
            "row_off": int(window.row_off),
            "width": int(window.width),
            "height": int(window.height),
        },
        "state_order": list(STATE_ORDER),
    }
    arrays: dict[str, np.ndarray] = {
        "metadata": np.asarray(json.dumps(metadata, sort_keys=True))
    }
    for index, state_weights in enumerate(states):
        arrays[f"indices_{index}"] = state_weights.flat_indices
        arrays[f"areas_{index}"] = state_weights.area_weights
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **arrays)
    return WeightSet(
        window=window,
        states=tuple(states),
        boundary_sha256=metadata["boundary_sha256"],
    )


def load_weights(path: Path, *, boundary_path: Path | None = None) -> WeightSet:
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"]))
        if metadata.get("schema_version") != WEIGHT_SCHEMA_VERSION:
            raise ValueError("Spatial weight schema is incompatible")
        if tuple(metadata.get("state_order", ())) != STATE_ORDER:
            raise ValueError("Spatial weight state order is incompatible")
        grid = metadata.get("grid", {})
        expected_grid = {
            "west": GRID_WEST,
            "north": GRID_NORTH,
            "resolution": GRID_RESOLUTION,
            "width": GRID_WIDTH,
            "height": GRID_HEIGHT,
        }
        if grid != expected_grid:
            raise ValueError("Spatial weight CHIRPS grid is incompatible")
        if boundary_path is not None and _sha256(boundary_path) != metadata["boundary_sha256"]:
            raise ValueError("Spatial weights do not match the configured boundary file")
        window_data = metadata["window"]
        window = Window(
            col_off=window_data["col_off"],
            row_off=window_data["row_off"],
            width=window_data["width"],
            height=window_data["height"],
        )
        states = tuple(
            StateWeights(
                state=state,
                flat_indices=archive[f"indices_{index}"].copy(),
                area_weights=archive[f"areas_{index}"].copy(),
            )
            for index, state in enumerate(STATE_ORDER)
        )
    return WeightSet(window=window, states=states, boundary_sha256=metadata["boundary_sha256"])
