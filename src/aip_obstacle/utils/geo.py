"""坐标与单位换算工具。纯函数，无副作用。"""

from __future__ import annotations

import re
from typing import Optional, Tuple

FEET_PER_METER = 3.28084
METERS_PER_NM = 1852.0
METERS_PER_KM = 1000.0

# 匹配 AIP 常见度分秒：DDMMSS.ssN/S  或  DDDMMSS.ssE/W
# 也接受分隔符形式： 39°48'12.3"N
_DMS_COMPACT = re.compile(
    r"^\s*(\d{2,3})(\d{2})(\d{2}(?:\.\d+)?)\s*([NSEW])\s*$",
    re.IGNORECASE,
)
_DMS_SYMBOLIC = re.compile(
    r"^\s*(\d{1,3})\s*[°º]\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:\.\d+)?)\s*[\"″]?\s*([NSEW])\s*$",
    re.IGNORECASE,
)


def dms_to_decimal(s: str) -> float:
    """把 AIP 常见的度分秒字符串转成十进制度（WGS84）。

    支持：
        "394812N"       -> 39.80333...
        "1161800.5E"    -> 116.30013...
        "39°48'12.3\"N" -> 39.80341...

    返回值：
        北纬 / 东经为正，南纬 / 西经为负。

    异常：
        无法解析时抛 ValueError。
    """
    if not isinstance(s, str):
        raise ValueError(f"dms_to_decimal: expected str, got {type(s).__name__}")

    text = s.strip()
    m = _DMS_COMPACT.match(text) or _DMS_SYMBOLIC.match(text)
    if not m:
        raise ValueError(f"dms_to_decimal: cannot parse {s!r}")

    deg = int(m.group(1))
    minutes = int(m.group(2))
    seconds = float(m.group(3))
    hemi = m.group(4).upper()

    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"dms_to_decimal: minute/second out of range in {s!r}")

    decimal = deg + minutes / 60.0 + seconds / 3600.0
    if hemi in ("S", "W"):
        decimal = -decimal
    return decimal


def feet_to_meter(value: float) -> float:
    """英尺 → 米。"""
    return value / FEET_PER_METER


def meter_to_feet(value: float) -> float:
    """米 → 英尺。"""
    return value * FEET_PER_METER


def distance_to_meter(value: float, unit: str) -> float:
    """把距离统一换算为米。

    支持单位：'m' / 'km' / 'NM' （大小写不敏感）。
    未知单位抛 ValueError。
    """
    u = unit.strip().lower()
    if u == "m":
        return float(value)
    if u == "km":
        return float(value) * METERS_PER_KM
    if u == "nm":
        return float(value) * METERS_PER_NM
    raise ValueError(f"distance_to_meter: unknown unit {unit!r}")


def height_to_meter(value: float, unit: str) -> float:
    """把高度统一换算为米。支持 'ft' / 'm'。"""
    u = unit.strip().lower()
    if u == "m":
        return float(value)
    if u == "ft":
        return feet_to_meter(float(value))
    raise ValueError(f"height_to_meter: unknown unit {unit!r}")


def normalize_whitespace(text: str) -> str:
    """把连续空白压成单空格，两端 strip。用于 raw_text 入库前规范化。"""
    return re.sub(r"\s+", " ", text).strip()


def try_dms_to_decimal(s: str) -> Optional[float]:
    """容错版：无法解析返回 None。"""
    try:
        return dms_to_decimal(s)
    except ValueError:
        return None


def parse_latlon_pair(lat_str: str, lon_str: str) -> Tuple[float, float]:
    """便捷封装：(lat_str, lon_str) → (lat_decimal, lon_decimal)。"""
    return dms_to_decimal(lat_str), dms_to_decimal(lon_str)


# ---------------------------------------------------------------------------
# 中国 AIP 前缀格式：N301733.4 / E1202547.2 / N303744 / E1203454
# ---------------------------------------------------------------------------

# 纬度：N + 2位度 + 2位分 + 2位秒[.小数]
_AIP_LAT_RE = re.compile(r"^N(\d{2})(\d{2})(\d{2}(?:\.\d+)?)$", re.IGNORECASE)
# 经度：E + 3位度 + 2位分 + 2位秒[.小数]
_AIP_LON_RE = re.compile(r"^E(\d{3})(\d{2})(\d{2}(?:\.\d+)?)$", re.IGNORECASE)


def parse_aip_lat(s: str) -> float:
    """解析中国 AIP 纬度字符串，如 N301733.4 或 N303744。

    返回十进制度（北纬为正）。无法解析时抛 ValueError。
    """
    m = _AIP_LAT_RE.match(s.strip())
    if not m:
        raise ValueError(f"parse_aip_lat: cannot parse {s!r}")
    deg = int(m.group(1))
    minutes = int(m.group(2))
    seconds = float(m.group(3))
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"parse_aip_lat: minute/second out of range in {s!r}")
    return deg + minutes / 60.0 + seconds / 3600.0


def parse_aip_lon(s: str) -> float:
    """解析中国 AIP 经度字符串，如 E1202547.2 或 E1203454。

    返回十进制度（东经为正）。无法解析时抛 ValueError。
    """
    m = _AIP_LON_RE.match(s.strip())
    if not m:
        raise ValueError(f"parse_aip_lon: cannot parse {s!r}")
    deg = int(m.group(1))
    minutes = int(m.group(2))
    seconds = float(m.group(3))
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"parse_aip_lon: minute/second out of range in {s!r}")
    return deg + minutes / 60.0 + seconds / 3600.0


def try_parse_aip_lat(s: str) -> Optional[float]:
    """容错版 parse_aip_lat，无法解析返回 None。"""
    try:
        return parse_aip_lat(s)
    except ValueError:
        return None


def try_parse_aip_lon(s: str) -> Optional[float]:
    """容错版 parse_aip_lon，无法解析返回 None。"""
    try:
        return parse_aip_lon(s)
    except ValueError:
        return None
