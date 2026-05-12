"""SQLite 存储层：schema 初始化 + 障碍物 / 失败记录读写。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from aip_obstacle.models import Obstacle, ParseFailure

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT    NOT NULL,
    file_hash       TEXT    NOT NULL UNIQUE,
    imported_at     TEXT    NOT NULL,
    total_candidates INTEGER DEFAULT 0,
    total_success   INTEGER DEFAULT 0,
    total_failed    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS obstacles (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id          INTEGER REFERENCES source_files(id),
    airport_icao            TEXT    NOT NULL,
    obstacle_id             TEXT    NOT NULL,
    name                    TEXT    NOT NULL,
    bearing_deg             REAL,
    distance_m              REAL,
    latitude                REAL,
    longitude               REAL,
    elevation_m             REAL,
    height_m                REAL,
    unit_distance_original  TEXT,
    unit_height_original    TEXT,
    mag_bearing_deg         REAL,
    confidence_score        REAL NOT NULL DEFAULT 0.0,
    source_page             INTEGER NOT NULL DEFAULT 0,
    raw_text                TEXT    NOT NULL,
    UNIQUE(airport_icao, obstacle_id, raw_text)
);

CREATE TABLE IF NOT EXISTS parse_failures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id  INTEGER REFERENCES source_files(id),
    airport_icao    TEXT    NOT NULL,
    source_page     INTEGER NOT NULL DEFAULT 0,
    raw_text        TEXT    NOT NULL,
    reason          TEXT    NOT NULL
);
"""


class SQLiteStore:
    """封装 SQLite 读写。使用标准库 sqlite3，不引入 ORM。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def file_already_imported(self, file_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT id FROM source_files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None

    def insert_source_file(
        self,
        file_path: str,
        file_hash: str,
        total_candidates: int,
        total_success: int,
        total_failed: int,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO source_files
                (file_path, file_hash, imported_at,
                 total_candidates, total_success, total_failed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                file_path,
                file_hash,
                datetime.now(timezone.utc).isoformat(),
                total_candidates,
                total_success,
                total_failed,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_obstacles(
        self, obstacles: List[Obstacle], source_file_id: Optional[int] = None
    ) -> int:
        """批量插入，遇到 UNIQUE 冲突则忽略。返回实际插入条数。"""
        inserted = 0
        for obs in obstacles:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO obstacles
                    (source_file_id, airport_icao, obstacle_id, name,
                     bearing_deg, distance_m, latitude, longitude,
                     elevation_m, height_m,
                     unit_distance_original, unit_height_original,
                     mag_bearing_deg, confidence_score,
                     source_page, raw_text)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source_file_id,
                    obs.airport_icao,
                    obs.obstacle_id,
                    obs.name,
                    obs.bearing_deg,
                    obs.distance_m,
                    obs.latitude,
                    obs.longitude,
                    obs.elevation_m,
                    obs.height_m,
                    obs.unit_distance_original,
                    obs.unit_height_original,
                    obs.mag_bearing_deg,
                    obs.confidence_score,
                    obs.source_page,
                    obs.raw_text,
                ),
            )
            inserted += cur.rowcount
        self._conn.commit()
        return inserted

    def fetch_all_obstacles(self) -> List[dict]:
        rows = self._conn.execute("SELECT * FROM obstacles ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def insert_failures(
        self, failures: List[ParseFailure], source_file_id: Optional[int] = None
    ) -> None:
        for f in failures:
            self._conn.execute(
                """
                INSERT INTO parse_failures
                    (source_file_id, airport_icao, source_page, raw_text, reason)
                VALUES (?,?,?,?,?)
                """,
                (source_file_id, f.airport_icao, f.source_page, f.raw_text, f.reason),
            )
        self._conn.commit()

    def fetch_all_failures(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM parse_failures ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def save_parse_result(self, result, source_file_id: Optional[int] = None) -> None:
        """便捷方法：把 ParseResult 里的 obstacles 和 failures 一次性写入。"""
        self.insert_obstacles(result.obstacles, source_file_id)
        self.insert_failures(result.failures, source_file_id)
