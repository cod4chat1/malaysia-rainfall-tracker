from __future__ import annotations

import html
import json
from pathlib import Path

from shapely.geometry import shape

SOURCE = Path("data/malaysia_adm1.geojson")
OUTPUT = Path("apps_script/MapPaths.html")
NAME_MAP = {"Malacca": "Melaka"}
SMALL_STATE_HIT_TARGETS = {"Kuala Lumpur", "Putrajaya", "Labuan", "Penang"}
MIN_X, MAX_X = 99.5, 119.5
MIN_Y, MAX_Y = 0.5, 7.5
WIDTH, HEIGHT = 960.0, 420.0


def project(longitude: float, latitude: float) -> tuple[float, float]:
    x = (longitude - MIN_X) / (MAX_X - MIN_X) * WIDTH
    y = (MAX_Y - latitude) / (MAX_Y - MIN_Y) * HEIGHT
    return x, y


def polygon_path(polygon) -> str:
    rings = [polygon.exterior, *polygon.interiors]
    commands: list[str] = []
    for ring in rings:
        points = [project(x, y) for x, y in ring.coords]
        if not points:
            continue
        commands.append(
            "M"
            + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)
            + " Z"
        )
    return " ".join(commands)


def main() -> None:
    collection = json.loads(SOURCE.read_text(encoding="utf-8"))
    groups: list[str] = []
    for feature in collection["features"]:
        state = NAME_MAP.get(
            feature["properties"]["shapeName"],
            feature["properties"]["shapeName"],
        )
        geometry = shape(feature["geometry"]).simplify(
            0.012,
            preserve_topology=True,
        )
        polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        path = " ".join(polygon_path(polygon) for polygon in polygons)
        hit_target = ""
        if state in SMALL_STATE_HIT_TARGETS:
            x, y = project(geometry.centroid.x, geometry.centroid.y)
            hit_target = (
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="8" '
                'fill="#fff" fill-opacity=".001"></circle>'
            )
        groups.append(
            f'<g class="state" data-state="{html.escape(state)}">'
            f'<path d="{path}" fill-rule="evenodd"></path>{hit_target}</g>'
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(groups) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
