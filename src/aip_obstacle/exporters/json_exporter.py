"""JSON 导出器：把 obstacles 写成 JSON 数组文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List


def export_json(obstacles: List[dict], out_path: str | Path) -> None:
    """把障碍物列表写成 JSON，缺字段为 null。"""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obstacles, f, ensure_ascii=False, indent=2, default=str)
