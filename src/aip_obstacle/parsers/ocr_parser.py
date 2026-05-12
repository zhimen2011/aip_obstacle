"""OCR 解析器占位。本期不实现，仅抛出 NotImplementedError。"""

from __future__ import annotations

from pathlib import Path
from typing import List

from aip_obstacle.models import TextBlock


def parse_ocr(path: str | Path) -> List[TextBlock]:  # noqa: ARG001
    raise NotImplementedError(
        "OCR 解析暂不支持。如需处理扫描版 PDF，请先用第三方工具转为文本型 PDF 或 TXT。"
    )
