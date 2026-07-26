from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .constants import STATE_ORDER

_ALIASES = {
    "johor": "Johor",
    "kedah": "Kedah",
    "kelantan": "Kelantan",
    "melaka": "Melaka",
    "malacca": "Melaka",
    "negeri sembilan": "Negeri Sembilan",
    "pahang": "Pahang",
    "pulau pinang": "Penang",
    "penang": "Penang",
    "perak": "Perak",
    "perlis": "Perlis",
    "sabah": "Sabah",
    "sarawak": "Sarawak",
    "selangor": "Selangor",
    "terengganu": "Terengganu",
    "trengganu": "Terengganu",
    "kuala lumpur": "Kuala Lumpur",
    "wilayah persekutuan kuala lumpur": "Kuala Lumpur",
    "putrajaya": "Putrajaya",
    "wilayah persekutuan putrajaya": "Putrajaya",
    "labuan": "Labuan",
    "wilayah persekutuan labuan": "Labuan",
}


def normalize_state_name(value: str) -> str:
    cleaned = unicodedata.normalize("NFKD", value)
    cleaned = " ".join(cleaned.casefold().replace("-", " ").split())
    try:
        return _ALIASES[cleaned]
    except KeyError as exc:
        raise ValueError(f"Unknown Malaysian ADM1 name: {value!r}") from exc


def _feature_name(properties: dict[str, Any]) -> str:
    for key in ("shapeName", "name", "NAME_1", "state"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise ValueError("Boundary feature has no recognized name property")


def load_boundaries(path: Path) -> dict[str, BaseGeometry]:
    document = json.loads(path.read_text(encoding="utf-8"))
    features = document.get("features")
    if not isinstance(features, list):
        raise ValueError("Boundary file must be a GeoJSON FeatureCollection")

    result: dict[str, BaseGeometry] = {}
    for feature in features:
        name = normalize_state_name(_feature_name(feature.get("properties", {})))
        geometry = shape(feature["geometry"])
        if geometry.is_empty:
            raise ValueError(f"Boundary for {name} is empty")
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if name in result:
            result[name] = result[name].union(geometry)
        else:
            result[name] = geometry

    missing = set(STATE_ORDER) - result.keys()
    unexpected = result.keys() - set(STATE_ORDER)
    if missing or unexpected:
        raise ValueError(
            f"Boundary areas mismatch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    return {name: result[name] for name in STATE_ORDER}

