"""测试：SQLite 存储层（storage/sqlite_store.py）。"""

import tempfile
from pathlib import Path

import pytest

from aip_obstacle.models import Obstacle, ParseFailure
from aip_obstacle.storage.sqlite_store import SQLiteStore


@pytest.fixture
def tmp_db(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    yield db
    db.close()


class TestSQLiteStore:
    def test_schema_created(self, tmp_db):
        rows = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in rows}
        assert "obstacles" in names
        assert "parse_failures" in names
        assert "source_files" in names

    def test_insert_and_fetch_obstacle(self, tmp_db):
        obs = Obstacle(
            airport_icao="ZBAA",
            obstacle_id="1",
            name="通信塔",
            bearing_deg=45.0,
            distance_m=2500.0,
            source_page=1,
            raw_text="1 通信塔 045° 2500m",
        )
        inserted = tmp_db.insert_obstacles([obs])
        assert inserted == 1
        rows = tmp_db.fetch_all_obstacles()
        assert len(rows) == 1
        assert rows[0]["name"] == "通信塔"

    def test_duplicate_ignored(self, tmp_db):
        obs = Obstacle(
            airport_icao="ZBAA",
            obstacle_id="1",
            name="通信塔",
            bearing_deg=45.0,
            distance_m=2500.0,
            source_page=1,
            raw_text="1 通信塔 045° 2500m",
        )
        tmp_db.insert_obstacles([obs])
        inserted2 = tmp_db.insert_obstacles([obs])
        assert inserted2 == 0  # 重复插入被忽略
        assert len(tmp_db.fetch_all_obstacles()) == 1

    def test_insert_failure(self, tmp_db):
        f = ParseFailure(
            airport_icao="ZBAA",
            source_page=2,
            raw_text="无法解析的行",
            reason="缺少定位信息",
        )
        tmp_db.insert_failures([f])
        rows = tmp_db.fetch_all_failures()
        assert len(rows) == 1
        assert rows[0]["reason"] == "缺少定位信息"

    def test_file_already_imported(self, tmp_db):
        assert not tmp_db.file_already_imported("abc123")
        tmp_db.insert_source_file(
            file_path="test.txt",
            file_hash="abc123",
            total_candidates=5,
            total_success=4,
            total_failed=1,
        )
        assert tmp_db.file_already_imported("abc123")

    def test_context_manager(self, tmp_path):
        with SQLiteStore(tmp_path / "ctx.sqlite") as store:
            obs = Obstacle(
                airport_icao="ZSPD",
                obstacle_id="2",
                name="水塔",
                bearing_deg=90.0,
                distance_m=1000.0,
                source_page=1,
                raw_text="2 水塔 090° 1000m",
            )
            store.insert_obstacles([obs])
            assert len(store.fetch_all_obstacles()) == 1
