"""端到端冒烟测试：从 TXT 样例文件解析 -> 写库 -> 导出三种格式。"""

import json
import csv
from pathlib import Path

import pytest

from aip_obstacle.pipeline import parse_text, parse_file
from aip_obstacle.storage.sqlite_store import SQLiteStore
from aip_obstacle.exporters.csv_exporter import export_csv, export_failures_csv
from aip_obstacle.exporters.json_exporter import export_json
from aip_obstacle.exporters.geojson_exporter import export_geojson

# 最小样例文本（模拟中国 AIP 障碍物表片段）
SAMPLE_TEXT = """\
ZBAA – BEIJING/Capital International Airport
AD 2.10 OBSTACLES IN THE APPROACH AND TAKE-OFF AREAS

编号  名称          方位    距离    高度
1     通信塔        045°    2500m   120m
2     烟囱          090°    1200m   80m
3     394812N 1161800E 大楼  高度 150m
"""


@pytest.fixture
def sample_txt(tmp_path):
    p = tmp_path / "sample_aip.txt"
    p.write_text(SAMPLE_TEXT, encoding="utf-8")
    return p


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "output"
    d.mkdir()
    return d


class TestEndToEnd:
    def test_parse_text_returns_result(self):
        result = parse_text(SAMPLE_TEXT, airport_icao="ZBAA")
        assert result.stats.total_candidates >= 1
        # 至少有一条成功解析
        assert result.stats.total_success >= 1

    def test_parse_file_txt(self, sample_txt):
        result = parse_file(sample_txt)
        assert result.stats.total_candidates >= 1

    def test_write_to_sqlite(self, out_dir):
        result = parse_text(SAMPLE_TEXT, airport_icao="ZBAA")
        db_path = out_dir / "aip_obstacle.sqlite"
        with SQLiteStore(db_path) as store:
            sf_id = store.insert_source_file(
                file_path="<text>",
                file_hash=result.file_hash,
                total_candidates=result.stats.total_candidates,
                total_success=result.stats.total_success,
                total_failed=result.stats.total_failed,
            )
            store.save_parse_result(result, source_file_id=sf_id)
            obstacles = store.fetch_all_obstacles()
        assert len(obstacles) >= 1
        assert obstacles[0]["airport_icao"] == "ZBAA"

    def test_no_duplicate_on_reimport(self, out_dir):
        result = parse_text(SAMPLE_TEXT, airport_icao="ZBAA")
        db_path = out_dir / "aip_obstacle.sqlite"
        with SQLiteStore(db_path) as store:
            store.insert_source_file(
                file_path="<text>",
                file_hash=result.file_hash,
                total_candidates=result.stats.total_candidates,
                total_success=result.stats.total_success,
                total_failed=result.stats.total_failed,
            )
            store.save_parse_result(result)
            count_first = len(store.fetch_all_obstacles())
            # 再次写入相同数据
            store.save_parse_result(result)
            count_second = len(store.fetch_all_obstacles())
        assert count_first == count_second

    def test_export_csv(self, out_dir):
        result = parse_text(SAMPLE_TEXT, airport_icao="ZBAA")
        db_path = out_dir / "aip_obstacle.sqlite"
        with SQLiteStore(db_path) as store:
            store.save_parse_result(result)
            obstacles = store.fetch_all_obstacles()
        csv_path = out_dir / "obstacles.csv"
        export_csv(obstacles, csv_path)
        assert csv_path.exists()
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
        assert len(rows) >= 1

    def test_export_json(self, out_dir):
        result = parse_text(SAMPLE_TEXT, airport_icao="ZBAA")
        db_path = out_dir / "aip_obstacle.sqlite"
        with SQLiteStore(db_path) as store:
            store.save_parse_result(result)
            obstacles = store.fetch_all_obstacles()
        json_path = out_dir / "obstacles.json"
        export_json(obstacles, json_path)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_export_geojson_only_with_coords(self, out_dir):
        result = parse_text(SAMPLE_TEXT, airport_icao="ZBAA")
        db_path = out_dir / "aip_obstacle.sqlite"
        with SQLiteStore(db_path) as store:
            store.save_parse_result(result)
            obstacles = store.fetch_all_obstacles()
        geo_path = out_dir / "obstacles.geojson"
        export_geojson(obstacles, geo_path)
        data = json.loads(geo_path.read_text(encoding="utf-8"))
        assert data["type"] == "FeatureCollection"
        # 所有 feature 都有经纬度
        for feat in data["features"]:
            coords = feat["geometry"]["coordinates"]
            assert coords[0] is not None
            assert coords[1] is not None

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_file("/nonexistent/path/file.txt")
