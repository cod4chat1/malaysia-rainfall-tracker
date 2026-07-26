from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse

import requests

APPROVED_HOST = "data.chc.ucsb.edu"
FINAL_COG_ROOT = (
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/cogs/"
)
FINAL_TIF_ROOT = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/"
PRELIM_TIF_ROOT = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/"

_HREF = re.compile(r"""href=["']([^"'?#]+)["']""", re.IGNORECASE)
_DATE = re.compile(r"(?P<year>19\d{2}|20\d{2})\.(?P<month>\d{2})\.(?P<day>\d{2})")


@dataclass(frozen=True)
class SourceAsset:
    day: date
    status: str
    url: str


def validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != APPROVED_HOST:
        raise ValueError(f"Unapproved source URL: {url}")


def parse_directory_listing(html: str, base_url: str) -> dict[date, str]:
    validate_source_url(base_url)
    assets: dict[date, str] = {}
    for href in _HREF.findall(html):
        match = _DATE.search(href)
        if not match or not href.lower().endswith((".tif", ".cog")):
            continue
        try:
            day = date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue
        url = urljoin(base_url, href)
        validate_source_url(url)
        assets[day] = url
    return assets


class CatalogClient:
    def __init__(
        self,
        *,
        timeout_seconds: int = 60,
        attempts: int = 4,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = "malaysia-rainfall-tracker/0.1"
        self._cache: dict[str, dict[date, str]] = {}

    def _listing(self, base_url: str) -> dict[date, str]:
        if base_url in self._cache:
            return self._cache[base_url]
        validate_source_url(base_url)
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.get(
                    base_url,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
                if response.status_code == 404:
                    return {}
                response.raise_for_status()
                result = parse_directory_listing(response.text, base_url)
                self._cache[base_url] = result
                return result
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self.attempts:
                    time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"Could not read CHIRPS catalog {base_url}") from last_error

    def assets_for_year(self, year: int) -> tuple[dict[date, str], dict[date, str]]:
        final = self._listing(f"{FINAL_COG_ROOT}{year}/")
        if not final:
            final = self._listing(f"{FINAL_TIF_ROOT}{year}/")
        prelim = self._listing(f"{PRELIM_TIF_ROOT}{year}/")
        return final, prelim

    def preferred_asset(self, day: date) -> SourceAsset | None:
        final, prelim = self.assets_for_year(day.year)
        if day in final:
            return SourceAsset(day, "CHIRPS_V3_FINAL_RNL", final[day])
        if day in prelim:
            return SourceAsset(day, "CHIRPS_V3_PRELIM_SAT", prelim[day])
        return None


def should_process(existing_status: str | None, asset: SourceAsset | None) -> bool:
    if asset is None:
        return False
    if not existing_status:
        return True
    return (
        existing_status == "CHIRPS_V3_PRELIM_SAT"
        and asset.status == "CHIRPS_V3_FINAL_RNL"
    )

