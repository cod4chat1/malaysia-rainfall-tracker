from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class Settings:
    boundary_path: Path
    weights_path: Path
    lookback_days: int = 62
    max_dates_per_run: int = 10
    max_download_bytes: int = 50_000_000
    max_total_download_bytes: int = 250_000_000
    max_sheets_requests: int = 50
    min_valid_area_pct: float = 95.0
    request_timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            boundary_path=Path(
                os.getenv("RAINFALL_BOUNDARY_PATH", "data/malaysia_adm1.geojson")
            ),
            weights_path=Path(
                os.getenv("RAINFALL_WEIGHTS_PATH", "data/chirps_v3_malaysia_weights.npz")
            ),
            lookback_days=_positive_int("RAINFALL_LOOKBACK_DAYS", 62),
            max_dates_per_run=_positive_int("RAINFALL_MAX_DATES_PER_RUN", 10),
            max_download_bytes=_positive_int("RAINFALL_MAX_DOWNLOAD_BYTES", 50_000_000),
            max_total_download_bytes=_positive_int(
                "RAINFALL_MAX_TOTAL_DOWNLOAD_BYTES", 250_000_000
            ),
            max_sheets_requests=_positive_int("RAINFALL_MAX_SHEETS_REQUESTS", 50),
            request_timeout_seconds=_positive_int("RAINFALL_REQUEST_TIMEOUT_SECONDS", 60),
        )


def spreadsheet_id_from_env() -> str:
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise ValueError("GOOGLE_SPREADSHEET_ID is required for Sheet operations")
    return spreadsheet_id


def service_account_info_from_env() -> dict[str, object]:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is required for Sheet operations")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("type") != "service_account":
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must contain a service-account key")
    return value
