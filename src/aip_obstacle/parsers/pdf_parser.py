"""PDF 解析器：文本提取 + 表格提取。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from aip_obstacle.models import TextBlock

_ICAO_PATTERN = re.compile(r"\b(Z[A-Z]{3})\b")


def _detect_icao(text: str) -> str:
    m = _ICAO_PATTERN.search(text)
    return m.group(1) if m else "UNKNOWN"


def parse_pdf(path: str | Path) -> List[TextBlock]:
    """解析文本型 PDF，每页输出一个 TextBlock。

    异常处理：
    - PDF 加密 → 抛 PermissionError
    - 无文本层（扫描件）→ 所有页 text 为空，调用方自行判断
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("请先安装 pdfplumber：pip install pdfplumber") from exc

    p = Path(path)
    blocks: List[TextBlock] = []
    last_icao = "UNKNOWN"

    with pdfplumber.open(str(p)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
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


def parse_pdf_tables(path: str | Path) -> List[List[Dict[str, Any]]]:
    """从 PDF 中提取表格数据（使用 pdfplumber.extract_tables）。

    返回 list of table groups，每个 group 是一个表格的完整行列表。
    每个 row dict 包含：
        - page: int              页码
        - airport_icao: str      ICAO 四字码
        - cells: List[str]       表格单元格
        - source_file: str       源文件路径

    如果 PDF 没有表格，返回空列表。
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("请先安装 pdfplumber：pip install pdfplumber") from exc

    p = Path(path)
    table_groups: List[List[Dict[str, Any]]] = []
    last_icao = "UNKNOWN"

    with pdfplumber.open(str(p)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            icao = _detect_icao(text)
            if icao == "UNKNOWN":
                icao = last_icao
            else:
                last_icao = icao

            tables = page.extract_tables()
            for table in tables:
                group: List[Dict[str, Any]] = []
                for row in table:
                    if row is None:
                        continue
                    group.append({
                        "page": page_num,
                        "airport_icao": icao,
                        "cells": row,
                        "source_file": str(p),
                    })
                if group:
                    table_groups.append(group)

    return table_groups
