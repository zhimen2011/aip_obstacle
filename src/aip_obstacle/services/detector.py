"""候选行识别器（detector）：从 TextBlock 列表中圈出疑似障碍物记录行。"""

from __future__ import annotations

import re
from typing import List

from aip_obstacle.models import CandidateRow, TextBlock

# 行首或靠前位置有编号模式：纯数字、"OBS-001" 类似、"（1）" 等
_ID_PATTERN = re.compile(r"^\s*(?:\d+|[A-Z]+-\d+|[（(]\d+[)）])", re.IGNORECASE)

# 高度相关：数字 + ft/m/米/英尺
_HEIGHT_PATTERN = re.compile(r"\d+\s*(?:ft|m|米|英尺)", re.IGNORECASE)

# 经纬度（度分秒紧凑格式 或 带°符号）
_COORD_PATTERN = re.compile(
    r"\d{2,3}\d{2}\d{2}(?:\.\d+)?[NSEW]"  # 紧凑：394812N
    r"|"
    r"\d{1,3}°\d{1,2}[\'′]\d{1,2}",       # 带符号：39°48'12"
    re.IGNORECASE,
)

# 方位 + 距离：数字 + 度/° 后跟数字 + 距离单位
_BEARING_DIST_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*°?\s+\d+(?:\.\d+)?\s*(?:km|m\b|NM)", re.IGNORECASE
)

# 明显是表头 / 页眉的行（中英文常见表头词）
_HEADER_PATTERN = re.compile(
    r"^[\s\-=*#─═]+$"           # 纯分隔符行
    r"|障碍物.{0,10}表"
    r"|OBSTACLE.{0,10}TABLE"
    r"|编\s*号.{0,10}名\s*称"
    r"|NO\.?\s+NAME"
    r"|PAGE\s+\d+"
    r"|AMDT\s+\d+",
    re.IGNORECASE,
)


def detect_candidates(blocks: List[TextBlock]) -> List[CandidateRow]:
    """从 TextBlock 列表中识别疑似障碍物行，返回 CandidateRow 列表。"""
    candidates: List[CandidateRow] = []

    for block in blocks:
        for line in block.text.splitlines():
            stripped = line.strip()
            if len(stripped) < 4:
                continue
            if _HEADER_PATTERN.search(stripped):
                continue

            has_id = bool(_ID_PATTERN.match(stripped))
            has_height = bool(_HEIGHT_PATTERN.search(stripped))
            has_coord = bool(_COORD_PATTERN.search(stripped))
            has_bearing_dist = bool(_BEARING_DIST_PATTERN.search(stripped))

            if has_id and (has_height or has_coord or has_bearing_dist):
                candidates.append(
                    CandidateRow(
                        raw_text=stripped,
                        source_page=block.page,
                        airport_icao=block.airport_icao,
                    )
                )

    return candidates
