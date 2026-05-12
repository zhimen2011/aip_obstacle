"""AIP 障碍物数据识别与结构化模块。

公共 API：
    parse_file(path)        -> ParseResult
    SQLiteStore(db_path)    -> 数据落库
    export_csv / export_json / export_geojson

见 docs/ 目录下的需求说明、数据流说明、项目结构说明。
"""

from aip_obstacle.models import (
    TextBlock,
    CandidateRow,
    Obstacle,
    ParseFailure,
    ParseStats,
    ParseResult,
)
from aip_obstacle.pipeline import parse_file, parse_text
from aip_obstacle.storage.sqlite_store import SQLiteStore
from aip_obstacle.exporters.csv_exporter import export_csv
from aip_obstacle.exporters.json_exporter import export_json
from aip_obstacle.exporters.geojson_exporter import export_geojson

__version__ = "0.1.0"

__all__ = [
    "TextBlock",
    "CandidateRow",
    "Obstacle",
    "ParseFailure",
    "ParseStats",
    "ParseResult",
    "parse_file",
    "parse_text",
    "SQLiteStore",
    "export_csv",
    "export_json",
    "export_geojson",
    "__version__",
]
