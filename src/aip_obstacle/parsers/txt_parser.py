"""TXT 文件解析器：读取纯文本文件，按换页符（\f）拆成 TextBlock 列表。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from aip_obstacle.models import TextBlock

# 中国 AIP 页眉中的 ICAO 四字码，例如 "ZBAA" "ZSPD" "ZGGG"
_ICAO_PATTERN = re.compile(r"\b(Z[A-Z]{3})\b")


def _detect_icao(text: str) -> str:
    """从文本中识别第一个出现的中国机场 ICAO 四字码（Z 开头）。"""
    m = _ICAO_PATTERN.search(text)
    return m.group(1) if m else "UNKNOWN"


def parse_txt(path: str | Path) -> List[TextBlock]:
    """读取 TXT 文件，返回 TextBlock 列表。

    - 按换页符 \\f 分页；无换页符则整个文件算第 1 页
    - 每页独立识别 ICAO；识别不到则继承上一页的值（兜底 UNKNOWN）
    """
    p = Path(path)
    with p.open("r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    pages = raw.split("\f") if "\f" in raw else [raw]

    blocks: List[TextBlock] = []
    last_icao = "UNKNOWN"
    for page_num, text in enumerate(pages, start=1):
        icao = _detect_icao(text)
        if icao == "UNKNOWN":
            icao = last_icao
        else:
            last_icao = icao
        blocks.append(
            TextBlock(
                page=page_num,
                text=text,
                source_file=str(p),
                airport_icao=icao,
            )
        )
    return blocks
