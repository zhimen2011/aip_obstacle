"""GeoJSON 导出器：仅导出经纬度齐全的障碍物记录。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("aip_obstacle")

_PROPERTIES_FIELDS = [
    "id", "source_file_id", "airport_icao", "obstacle_id", "name",
    "bearing_deg", "distance_m", "elevation_m", "height_m",
    "unit_distance_original", "unit_height_original",
    "source_page", "raw_text",
]


def export_geojson(obstacles: List[dict], out_path: str | Path) -> int:
    """把有经纬度的障碍物写成 GeoJSON FeatureCollection。

    返回跳过（无经纬度）的条数。
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    features = []
    skipped = 0
    for row in obstacles:
        lat = row.get("latitude")
        lon = row.get("longitude")
        if lat is None or lon is None:
            skipped += 1
            continue
        props = {k: row.get(k) for k in _PROPERTIES_FIELDS}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )

    collection = {"type": "FeatureCollection", "features": features}
    with p.open("w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2, default=str)

    if skipped:
        logger.warning("GeoJSON 导出：%d 条记录因缺少经纬度被跳过", skipped)
    return skipped
