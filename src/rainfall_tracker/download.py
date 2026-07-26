from __future__ import annotations

import contextlib
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.transform import Affine
from rasterio.windows import Window

from .catalog import validate_source_url
from .weights import GRID_HEIGHT, GRID_NORTH, GRID_RESOLUTION, GRID_WEST, GRID_WIDTH


@dataclass
class DownloadBudget:
    per_file_bytes: int
    total_bytes: int
    used_bytes: int = 0

    def reserve(self, size: int) -> None:
        if size > self.per_file_bytes:
            raise ValueError(f"Source file exceeds per-file limit: {size} bytes")
        if self.used_bytes + size > self.total_bytes:
            raise ValueError("Run would exceed total download limit")

    def consume(self, size: int) -> None:
        self.used_bytes += size
        if self.used_bytes > self.total_bytes:
            raise ValueError("Run exceeded total download limit")


def _expected_transform() -> Affine:
    return Affine(GRID_RESOLUTION, 0.0, GRID_WEST, 0.0, -GRID_RESOLUTION, GRID_NORTH)


def _validate_raster(dataset: rasterio.io.DatasetReader) -> None:
    if dataset.width != GRID_WIDTH or dataset.height != GRID_HEIGHT:
        raise ValueError(
            f"Unexpected CHIRPS dimensions: {dataset.width}x{dataset.height}"
        )
    if dataset.crs is None or dataset.crs.to_epsg() != 4326:
        raise ValueError(f"Unexpected CHIRPS CRS: {dataset.crs}")
    if not dataset.transform.almost_equals(_expected_transform(), precision=1e-8):
        raise ValueError(f"Unexpected CHIRPS transform: {dataset.transform}")
    if dataset.count != 1:
        raise ValueError(f"Expected one CHIRPS band, found {dataset.count}")


def _read_dataset(path_or_url: str | Path, window: Window) -> np.ndarray:
    with rasterio.open(path_or_url) as dataset:
        _validate_raster(dataset)
        masked = dataset.read(1, window=window, masked=True)
        return np.asarray(masked.filled(np.nan), dtype=np.float64)


def _download(
    url: str,
    target: Path,
    *,
    budget: DownloadBudget,
    timeout_seconds: int,
    attempts: int = 4,
) -> None:
    validate_source_url(url)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with requests.get(
                url,
                stream=True,
                timeout=timeout_seconds,
                allow_redirects=False,
                headers={"User-Agent": "malaysia-rainfall-tracker/0.1"},
            ) as response:
                response.raise_for_status()
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared:
                    budget.reserve(declared)
                downloaded = 0
                with target.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > budget.per_file_bytes:
                            raise ValueError("Source exceeded per-file download limit")
                        if budget.used_bytes + downloaded > budget.total_bytes:
                            raise ValueError("Run exceeded total download limit")
                        handle.write(chunk)
                budget.consume(downloaded)
                return
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            with contextlib.suppress(OSError):
                target.unlink()
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 8))
    raise RuntimeError(f"Could not download {url}") from last_error


def read_raster_window(
    url: str,
    window: Window,
    *,
    budget: DownloadBudget,
    timeout_seconds: int = 60,
) -> np.ndarray:
    validate_source_url(url)
    if url.lower().endswith(".cog"):
        try:
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".cog,.tif",
                GDAL_HTTP_MAX_RETRY="3",
                GDAL_HTTP_RETRY_DELAY="1",
            ):
                return _read_dataset(url, window)
        except (rasterio.errors.RasterioError, ValueError):
            pass

    suffix = Path(url).suffix or ".tif"
    with tempfile.TemporaryDirectory(prefix="rainfall-tracker-") as directory:
        target = Path(directory) / f"source{suffix}"
        _download(
            url,
            target,
            budget=budget,
            timeout_seconds=timeout_seconds,
        )
        return _read_dataset(target, window)

