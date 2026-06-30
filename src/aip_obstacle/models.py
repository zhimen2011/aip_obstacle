"""中间数据结构。

规则：
- 所有跨模块传递的数据用 dataclass 显式声明，不传 dict。
- 可选字段统一使用 Optional[...] = None，None 表示「AIP 原文未提供」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TextBlock:
    """文本抽取阶段的单位。通常一页 PDF 或一整个 TXT 对应一个 TextBlock。"""

    page: int
    text: str
    source_file: str
    airport_icao: str = "UNKNOWN"


@dataclass
class CandidateRow:
    """识别阶段输出。表示一行疑似障碍物记录。"""

    raw_text: str
    source_page: int
    airport_icao: str


@dataclass
class Obstacle:
    """结构化后的障碍物记录。

    必填：airport_icao / obstacle_id / name / source_page / raw_text
    可选：定位信息（方位+距离 或 经纬度 至少一组由 field_parser 保证）
    """

    airport_icao: str
    obstacle_id: str
    name: str

    bearing_deg: Optional[float] = None
    distance_m: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    elevation_m: Optional[float] = None
    height_m: Optional[float] = None

    unit_distance_original: Optional[str] = None
    unit_height_original: Optional[str] = None
    bearing_note: Optional[str] = None

    # AIP 来源的磁方位（MAG），与 bearing_deg（真方位）并存
    mag_bearing_deg: Optional[float] = None

    # 解析置信度 0.0-1.0
    confidence_score: float = 0.0

    # 人工修正状态。True 表示至少有一个字段在软件界面中被人工改过。
    is_user_modified: bool = False
    edited_at: Optional[str] = None

    source_page: int = 0
    raw_text: str = ""


@dataclass
class ParseFailure:
    """解析失败记录。保留 raw_text 以便人工复核。"""

    airport_icao: str
    source_page: int
    raw_text: str
    reason: str


@dataclass
class ParseStats:
    """单次解析的统计。"""

    total_candidates: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_no_coord: int = 0


@dataclass
class ParseResult:
    """pipeline.parse_file 的输出。"""

    source_file: str
    file_hash: str
    obstacles: List[Obstacle] = field(default_factory=list)
    failures: List[ParseFailure] = field(default_factory=list)
    stats: ParseStats = field(default_factory=ParseStats)
