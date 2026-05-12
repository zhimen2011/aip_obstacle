"""中国 AIP PDF 障碍物解析器（表格解析 + 行级解析）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from aip_obstacle.models import Obstacle, ParseFailure, TextBlock
from aip_obstacle.utils.geo import try_parse_aip_lat, try_parse_aip_lon

_WATERMARK_PREFIX = re.compile(r"^[©CALIGHRSVDET.\s]{0,5}")
_ANCHOR_RE = re.compile(r"^[©CALIGHRSVDET.\s]{0,5}(\d{3})\s*(?:(\d{3})/(\d+))?[^/\d]*$")
_BRG_DIST_RE = re.compile(r"^[©CALIGHRSVDET.\s]{0,5}(\d{3})/(\d+)")
_LAT_LINE_RE = re.compile(r"(N\d{6,8}(?:\.\d+)?)")
_LON_IN_LINE_RE = re.compile(r"(E\d{7,9}(?:\.\d+)?)")
_ELEV_AFTER_LON_RE = re.compile(r"E\d{7,9}(?:\.\d+)?\s+(\d+(?:\.\d+)?)")

_SKIP_LINE_RE = re.compile(
    r"中国民航国内航空资料汇编"
    r"|NAIP\s+Z[A-Z]{3}"
    r"|Obstacles?\s+within"
    r"|半径\d+\s*千米"
    r"|障碍物位置|障碍物名称|障碍物标志"
    r"|Obstacle\s+(ID|position|marking|type)"
    r"|MAG\s*/\s*\(Height\)"
    r"|BRG\(degree\)"
    r"|Flight\s+procedure"
    r"|Designation\s+type"
    r"|EFF\d{4}-\d{2}-\d{2}"
    r"|订购单位"
    r"|中国民用航空局"
    r"|CAAC"
    r"|^\s*\d{4}-\d{1,2}-\d{1,2}\s*$"
    r"|^\s*[1-6]\s*$",
    re.IGNORECASE,
)

_OBSTACLE_TYPES = frozenset({
    "山", "建筑", "天线", "塔", "杆", "水塔", "工业烟囱", "导航台",
    "标志牌", "高压输电线", "电气外部照明",
})


def _strip_watermark(line: str) -> str:
    return _WATERMARK_PREFIX.sub("", line).strip()


def _is_skip_line(line: str) -> bool:
    return bool(_SKIP_LINE_RE.search(line))


def _extract_name_from_text(text: str) -> Optional[str]:
    clean = _strip_watermark(text)
    clean = _LON_IN_LINE_RE.sub("", clean)
    clean = _LAT_LINE_RE.sub("", clean)
    clean = re.sub(r"\s+\d+(?:\.\d+)?\s*$", "", clean)
    # 只有整行就是类型词时才删除（避免把「青龙山」里的「山」删掉）
    stripped = clean.strip()
    if stripped in _OBSTACLE_TYPES:
        return None
    clean = re.sub(r"\s*RWY.*$", "", clean, flags=re.IGNORECASE)
    clean = clean.strip("） ）()（ ")
    return clean if clean else None


def _calc_confidence(
    lat: Optional[float],
    lon: Optional[float],
    mag_brg: Optional[float],
    dist: Optional[float],
    elev: Optional[float],
) -> float:
    # 方位距离是必须字段，到这里一定有值，作为基础分
    score = 0.6
    if lat is not None and lon is not None:
        score += 0.3
    if elev is not None:
        score += 0.1
    return min(score, 1.0)


# --- 内容驱动解析的正则与常量 ---
_BRG_DIST_PATTERN = re.compile(r"(\d{2,3})/(\d+)")
_LAT_PATTERN = re.compile(r"N(\d{6,8}(?:\.\d+)?)")
_LON_PATTERN = re.compile(r"E(\d{7,9}(?:\.\d+)?)")
_IS_PURE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_IS_DIGITS = re.compile(r"^\d+$")

_SKIP_KEYWORDS = [
    "障碍物名称", "障碍物类", "障碍物位置",
    "Obstacle ID", "Obstacle type", "Obstacle position",
    "MAG", "BRG", "Designation", "Flight procedure",
    "半径", "千米", "中国民航", "CAAC",
    "EFF", "订购单位", "Obstacles within",
    "take-off", "Elevation", "Colour",
    "备注", "说明", "注：", "注:",
]


def _first_non_empty(cells: List[str]) -> str:
    for cell in cells:
        if cell and str(cell).strip():
            return str(cell).strip()
    return ""


def _is_data_row(cells: List[str]) -> bool:
    """数据行判定：第一个非空 cell 的 \\n 分割最后一段是纯数字。"""
    first = _first_non_empty(cells)
    if not first:
        return False
    parts = [p.strip() for p in first.split("\n") if p.strip()]
    if len(parts) < 2:
        return False
    return bool(_IS_DIGITS.match(parts[-1]))


def _is_continuation_row(cells: List[str]) -> bool:
    """续行判定：只有 0-1 个非空 cell，且整行不构成数据行。"""
    non_empty = [c for c in cells if c and str(c).strip()]
    return 0 < len(non_empty) <= 1


def _is_skip_row(cells: List[str]) -> bool:
    """跳过行判定：含已知表头/章节关键词。"""
    text = " ".join(str(c or "") for c in cells)
    text_lower = text.lower()
    for kw in _SKIP_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


def _merge_rows(group: List[dict]) -> List[dict]:
    """合并被拆分的行。续行拼回上一行对应列。"""
    merged: List[dict] = []
    for row in group:
        cells = row["cells"]
        # 优先排除章节标题/表头/备注等非数据行
        if _is_skip_row(cells):
            continue
        if _is_data_row(cells):
            merged.append({
                **row,
                "cells": [str(c).strip() if c else "" for c in cells],
            })
        elif _is_continuation_row(cells):
            if merged:
                last_cells = merged[-1]["cells"]
                for i, cell in enumerate(cells):
                    if cell and str(cell).strip():
                        existing = last_cells[i] if i < len(last_cells) else ""
                        val = str(cell).strip()
                        last_cells[i] = (existing + "\n" + val) if existing else val
        # else: skip (empty / unrecognized)
    return merged


def _find_brg_dist(cells: List[str]) -> tuple:
    """全行搜索方位/距离，返回 (mag_brg, dist_m, cell_index)。未找到返回 (None, None, -1)。"""
    for i, cell in enumerate(cells):
        if not cell:
            continue
        m = _BRG_DIST_PATTERN.search(str(cell))
        if m:
            brg = float(m.group(1))
            dist = float(m.group(2))
            if 0 <= brg <= 360:
                return brg, dist, i
    return None, None, -1


def _find_elevation(cells: List[str], after_idx: int) -> Optional[float]:
    """在指定列之后找第一个纯数字（200-6000 范围优先，超出范围也接受）。"""
    for i in range(after_idx + 1, len(cells)):
        if not cells[i]:
            continue
        text = str(cells[i]).strip()
        if _IS_PURE_NUMBER.match(text):
            val = float(text)
            if 200 <= val <= 6000:
                return val
    # 放宽范围再找一次
    for i in range(after_idx + 1, len(cells)):
        if not cells[i]:
            continue
        text = str(cells[i]).strip()
        if _IS_PURE_NUMBER.match(text):
            return float(text)
    return None


def _find_lat_lon(cells: List[str]) -> tuple:
    """全行搜索经纬度，返回 (lat, lon)，均为 None 表示未找到。"""
    for cell in cells:
        if not cell:
            continue
        text = str(cell)
        lat_m = _LAT_PATTERN.search(text)
        lon_m = _LON_PATTERN.search(text)
        if lat_m and lon_m:
            lat = try_parse_aip_lat(lat_m.group(0))
            lon = try_parse_aip_lon(lon_m.group(0))
            return lat, lon
    return None, None


def _find_type(cells: List[str], name_cell_text: str, bd_idx: int) -> str:
    """在方位/距离列之前找障碍物类型（非名称的非空文本）。"""
    for i in range(min(2, len(cells)), bd_idx):
        if not cells[i]:
            continue
        text = str(cells[i]).strip()
        if text and text != name_cell_text and not _BRG_DIST_PATTERN.search(text):
            return text
    return ""


def _is_obstacle_table(group: List[dict]) -> bool:
    """判断是否为障碍物数据表：至少有一行同时满足名称+编号格式和方位/距离格式。"""
    for row in group:
        cells = row["cells"]
        if _is_data_row(cells) and _find_brg_dist(cells)[0] is not None:
            return True
    return False


# ---------------------------------------------------------------------------
# 主解析函数
# ---------------------------------------------------------------------------


def parse_aip_table_rows(
    table_groups: List[List[Dict[str, Any]]],
) -> tuple[List[Obstacle], List[ParseFailure]]:
    """内容驱动的通用表格解析器。

    不依赖列位置，通过全行搜索目标模式（方位/距离、标高、经纬度）
    来解析中国 AIP 障碍物数据表。适配 ZLXY / ZUTF / ZSHC 等不同
    机场的表格列数、列序、单元格格式差异。
    """
    obstacles: List[Obstacle] = []
    failures: List[ParseFailure] = []

    for group in table_groups:
        if not _is_obstacle_table(group):
            continue

        merged = _merge_rows(group)

        for row in merged:
            result = _parse_one_row(row)
            if isinstance(result, Obstacle):
                obstacles.append(result)
            else:
                failures.append(result)

    return obstacles, failures


def _parse_one_row(row: Dict[str, Any]) -> Obstacle | ParseFailure:
    """解析一条合并后的数据行。"""
    cells: List[str] = row["cells"]
    page: int = row["page"]
    icao: str = row["airport_icao"]

    # --- 名称 + 编号 ---
    first = _first_non_empty(cells)
    parts = [p.strip() for p in first.split("\n") if p.strip()]
    if not parts:
        return ParseFailure(
            airport_icao=icao,
            source_page=page,
            raw_text=" | ".join(str(c) for c in cells),
            reason="第一个非空单元格为空，无法提取编号和名称",
        )

    obstacle_id = parts[-1]
    name = " ".join(parts[:-1]) if len(parts) > 1 else obstacle_id

    # --- 方位/距离 ---
    mag_brg, dist_m, bd_idx = _find_brg_dist(cells)
    if mag_brg is None:
        return ParseFailure(
            airport_icao=icao,
            source_page=page,
            raw_text=" | ".join(str(c) for c in cells),
            reason=f"编号 {obstacle_id}：缺少方位/距离",
        )

    # --- 标高 ---
    elev = _find_elevation(cells, bd_idx)

    # --- 经纬度 ---
    lat, lon = _find_lat_lon(cells)

    # --- 类型 ---
    obstacle_type = _find_type(cells, first, bd_idx)

    # --- 原始文本 ---
    raw_text = " | ".join(str(c) for c in cells)

    # --- 置信度 ---
    confidence = 0.7
    if lat is not None and lon is not None:
        confidence += 0.15
    if elev is not None:
        confidence += 0.1
    if obstacle_type:
        confidence += 0.05
    confidence = min(confidence, 1.0)

    return Obstacle(
        airport_icao=icao,
        obstacle_id=obstacle_id,
        name=name,
        bearing_deg=None,
        mag_bearing_deg=mag_brg,
        distance_m=dist_m,
        latitude=lat,
        longitude=lon,
        elevation_m=elev,
        height_m=None,
        unit_distance_original="m",
        unit_height_original="m" if elev is not None else None,
        confidence_score=confidence,
        source_page=page,
        raw_text=raw_text,
    )


def _parse_record(
    lines: List[str],
    anchor_idx: int,
    obstacle_id: str,
    mag_brg_from_anchor: Optional[float],
    dist_from_anchor: Optional[float],
    airport_icao: str,
    source_page: int,
) -> "Obstacle | ParseFailure":
    lon_line_idx: Optional[int] = None
    # 先向上找经度行
    for i in range(anchor_idx - 1, max(anchor_idx - 6, -1), -1):
        if _LON_IN_LINE_RE.search(lines[i]):
            lon_line_idx = i
            break
    # 向上找不到时，向下找（倒置格式：编号行在经度行上方）
    if lon_line_idx is None:
        for i in range(anchor_idx + 1, min(anchor_idx + 3, len(lines))):
            if _LON_IN_LINE_RE.search(lines[i]):
                lon_line_idx = i
                break

    lat_line_idx: Optional[int] = None
    search_from = lon_line_idx if lon_line_idx is not None else anchor_idx
    for i in range(search_from - 1, max(search_from - 4, -1), -1):
        if _LAT_LINE_RE.search(lines[i]):
            lat_line_idx = i
            break

    lon: Optional[float] = None
    elev: Optional[float] = None
    if lon_line_idx is not None:
        lon_line = lines[lon_line_idx]
        m_lon = _LON_IN_LINE_RE.search(lon_line)
        if m_lon:
            lon = try_parse_aip_lon(m_lon.group(1))
        m_elev = _ELEV_AFTER_LON_RE.search(lon_line)
        if m_elev:
            try:
                elev = float(m_elev.group(1))
            except ValueError:
                pass

    lat: Optional[float] = None
    if lat_line_idx is not None:
        m_lat = _LAT_LINE_RE.search(lines[lat_line_idx])
        if m_lat:
            lat = try_parse_aip_lat(m_lat.group(1))

    top_idx = lat_line_idx if lat_line_idx is not None else (
        lon_line_idx if lon_line_idx is not None else anchor_idx - 1
    )
    name_parts: List[str] = []
    for i in range(top_idx, anchor_idx):
        line = lines[i]
        if _is_skip_line(line):
            continue
        part = _extract_name_from_text(line)
        if part:
            name_parts.append(part)
    name: Optional[str] = "".join(name_parts) if name_parts else None

    mag_brg = mag_brg_from_anchor
    dist_m = dist_from_anchor
    if mag_brg is None:
        # 向下看最多 3 行，跳过空行，找方位/距离行
        for look_ahead in range(1, 4):
            next_idx = anchor_idx + look_ahead
            if next_idx >= len(lines):
                break
            next_line = lines[next_idx]
            if not next_line.strip():
                continue
            m_bd = _BRG_DIST_RE.match(next_line)
            if m_bd:
                try:
                    mag_brg = float(m_bd.group(1))
                    dist_m = float(m_bd.group(2))
                except ValueError:
                    pass
                break

    raw_lines = []
    for i in range(max(0, top_idx), min(len(lines), anchor_idx + 2)):
        raw_lines.append(lines[i].strip())
    raw_text = " | ".join(l for l in raw_lines if l)

    # 方位距离是必须字段；经纬度有则用，无则留 None
    if mag_brg is None or dist_m is None:
        return ParseFailure(
            airport_icao=airport_icao,
            source_page=source_page,
            raw_text=raw_text,
            reason=f"编号 {obstacle_id}：缺少方位/距离",
        )

    confidence = _calc_confidence(lat, lon, mag_brg, dist_m, elev)

    return Obstacle(
        airport_icao=airport_icao,
        obstacle_id=obstacle_id,
        name=name or "",
        bearing_deg=None,
        mag_bearing_deg=mag_brg,
        distance_m=dist_m,
        latitude=lat,
        longitude=lon,
        elevation_m=elev,
        height_m=None,
        unit_distance_original="m" if dist_m is not None else None,
        unit_height_original="m" if elev is not None else None,
        confidence_score=confidence,
        source_page=source_page,
        raw_text=raw_text,
    )


def _filter_lines(text: str) -> List[str]:
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue
        if _is_skip_line(stripped):
            result.append("")
            continue
        result.append(line)
    return result


def parse_blocks_aip(
    blocks: List[TextBlock],
) -> tuple[List[Obstacle], List[ParseFailure]]:
    obstacles: List[Obstacle] = []
    failures: List[ParseFailure] = []

    for block in blocks:
        lines = _filter_lines(block.text)
        n = len(lines)
        i = 0
        while i < n:
            line = lines[i]
            m = _ANCHOR_RE.match(line.strip())
            if m:
                obstacle_id = m.group(1)
                mag_brg: Optional[float] = None
                dist_m: Optional[float] = None
                if m.group(2) and m.group(3):
                    try:
                        mag_brg = float(m.group(2))
                        dist_m = float(m.group(3))
                    except ValueError:
                        pass
                record = _parse_record(
                    lines=lines,
                    anchor_idx=i,
                    obstacle_id=obstacle_id,
                    mag_brg_from_anchor=mag_brg,
                    dist_from_anchor=dist_m,
                    airport_icao=block.airport_icao,
                    source_page=block.page,
                )
                if isinstance(record, Obstacle):
                    obstacles.append(record)
                else:
                    failures.append(record)
            i += 1

    return obstacles, failures
