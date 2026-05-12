"""CSV 导出器：把 obstacles 和 parse_failures 写成 CSV 文件。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

_OBSTACLE_FIELDS = [
    "id", "source_file_id", "airport_icao", "obstacle_id", "name",
    "bearing_deg", "mag_bearing_deg", "distance_m",
    "latitude", "longitude",
    "elevation_m", "height_m",
    "unit_distance_original", "unit_height_original",
    "confidence_score",
    "source_page", "raw_text",
]

_FAILURE_FIELDS = [
    "id", "source_file_id", "airport_icao", "source_page", "raw_text", "reason",
]


def export_csv(obstacles: List[dict], out_path: str | Path) -> None:
    """把障碍物列表写成 CSV，缺字段留空。"""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_OBSTACLE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in obstacles:
            writer.writerow({k: row.get(k, "") for k in _OBSTACLE_FIELDS})


def export_failures_csv(failures: List[dict], out_path: str | Path) -> None:
    """把解析失败记录写成 CSV。"""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_FAILURE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in failures:
            writer.writerow({k: row.get(k, "") for k in _FAILURE_FIELDS})
