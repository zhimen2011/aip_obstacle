"""字段解析器（field_parser）：从 CandidateRow 的 raw_text 中提取各字段。"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from aip_obstacle.models import CandidateRow, Obstacle, ParseFailure
from aip_obstacle.utils.geo import (
    distance_to_meter,
    height_to_meter,
    normalize_whitespace,
    try_dms_to_decimal,
)

# --- 编号：行首数字或字母+数字组合 ---
_ID_RE = re.compile(r"^\s*(\d+|[A-Z]+-\d+|[（(]\d+[)）])\s*", re.IGNORECASE)

# --- 名称：编号之后的中文/英文词组（贪婪，到下一个数字段或末尾） ---
_NAME_RE = re.compile(r"^([一-鿿A-Za-z][一-鿿A-Za-z\s\-/（）()]{0,60})")

# --- 方位：0-360 的数字，后接 ° 或 "度"（° 是非单词字符，不用 \b 结尾）---
_BEARING_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*(?:°|度)")

# --- 距离：数字 + 单位 ---
_DIST_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(km|m\b|NM)\b", re.IGNORECASE)

# --- 高度 / 海拔：数字 + ft/m ---
_HEIGHT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(ft|m)\b", re.IGNORECASE)

# --- 经纬度（紧凑度分秒） ---
_LAT_RE = re.compile(r"(\d{6}(?:\.\d+)?[NS])", re.IGNORECASE)
_LON_RE = re.compile(r"(\d{7}(?:\.\d+)?[EW])", re.IGNORECASE)


def _extract_id(text: str) -> Tuple[Optional[str], str]:
    """提取编号，返回 (obstacle_id, 剩余文本)。"""
    m = _ID_RE.match(text)
    if not m:
        return None, text
    oid = m.group(1).strip("（()）")
    return oid, text[m.end():]


def _extract_name(text: str) -> Tuple[Optional[str], str]:
    """提取名称，返回 (name, 剩余文本)。"""
    m = _NAME_RE.match(text.strip())
    if not m:
        return None, text
    name = m.group(1).strip()
    return name if name else None, text[m.end():]


def _extract_bearing(text: str) -> Optional[float]:
    m = _BEARING_RE.search(text)
    if not m:
        return None
    val = float(m.group(1))
    return val if 0.0 <= val <= 360.0 else None


def _extract_distance(text: str) -> Tuple[Optional[float], Optional[str]]:
    m = _DIST_RE.search(text)
    if not m:
        return None, None
    val = float(m.group(1))
    unit = m.group(2)
    try:
        return distance_to_meter(val, unit), unit
    except ValueError:
        return None, None


def _extract_height(text: str) -> Tuple[Optional[float], Optional[str]]:
    """提取最后一个高度值（通常靠后的是标高/高度）。"""
    matches = list(_HEIGHT_RE.finditer(text))
    if not matches:
        return None, None
    m = matches[-1]
    val = float(m.group(1))
    unit = m.group(2)
    try:
        return height_to_meter(val, unit), unit
    except ValueError:
        return None, None


def _extract_latlon(text: str) -> Tuple[Optional[float], Optional[float]]:
    lat_m = _LAT_RE.search(text)
    lon_m = _LON_RE.search(text)
    lat = try_dms_to_decimal(lat_m.group(1)) if lat_m else None
    lon = try_dms_to_decimal(lon_m.group(1)) if lon_m else None
    return lat, lon


def parse_candidate(row: CandidateRow) -> Obstacle | ParseFailure:
    """把一条 CandidateRow 解析成 Obstacle 或 ParseFailure。"""
    text = normalize_whitespace(row.raw_text)

    obstacle_id, remaining = _extract_id(text)
    name, _ = _extract_name(remaining)

    bearing = _extract_bearing(text)
    distance_m, dist_unit = _extract_distance(text)
    height_m, height_unit = _extract_height(text)
    lat, lon = _extract_latlon(text)

    # 编号和名称都必须有
    if not obstacle_id or not name:
        return ParseFailure(
            airport_icao=row.airport_icao,
            source_page=row.source_page,
            raw_text=row.raw_text,
            reason=f"缺少{'编号' if not obstacle_id else '名称'}",
        )

    # 至少需要一组定位信息
    has_bearing_dist = bearing is not None and distance_m is not None
    has_latlon = lat is not None and lon is not None
    if not has_bearing_dist and not has_latlon:
        return ParseFailure(
            airport_icao=row.airport_icao,
            source_page=row.source_page,
            raw_text=row.raw_text,
            reason="缺少定位信息（方位+距离 或 经纬度 均无法识别）",
        )

    return Obstacle(
        airport_icao=row.airport_icao,
        obstacle_id=obstacle_id,
        name=name,
        bearing_deg=bearing,
        distance_m=distance_m,
        latitude=lat,
        longitude=lon,
        elevation_m=None,   # MVP 不单独区分 elevation vs height，统一存 height_m
        height_m=height_m,
        unit_distance_original=dist_unit,
        unit_height_original=height_unit,
        source_page=row.source_page,
        raw_text=row.raw_text,
    )
