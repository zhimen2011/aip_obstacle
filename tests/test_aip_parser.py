"""测试：中国 AIP 多行障碍物解析器（services/aip_parser.py）。"""
from __future__ import annotations
from pathlib import Path
import pytest
from aip_obstacle.models import Obstacle, ParseFailure, TextBlock
from aip_obstacle.services.aip_parser import parse_aip_table_rows, parse_blocks_aip
from aip_obstacle.utils.geo import parse_aip_lat, parse_aip_lon, try_parse_aip_lat, try_parse_aip_lon

_PDF_PATH = Path(__file__).parent.parent / "examples" / "ZSHC.pdf"
_SKIP_IF_NO_PDF = pytest.mark.skipif(not _PDF_PATH.exists(), reason="ZSHC.pdf not found")
_GUILIN_PDF = Path(__file__).parent.parent / "examples" / "\u6842\u6797.pdf"
_SKIP_IF_NO_GUILIN = pytest.mark.skipif(
    not _GUILIN_PDF.exists(),
    reason="Guilin example PDF not found",
)


class TestParseAipLatLon:
    def test_lat_with_decimal(self):
        r = parse_aip_lat("N301733.4")
        assert abs(r - (30 + 17/60 + 33.4/3600)) < 1e-6

    def test_lat_without_decimal(self):
        r = parse_aip_lat("N303744")
        assert abs(r - (30 + 37/60 + 44/3600)) < 1e-6

    def test_lon_with_decimal(self):
        r = parse_aip_lon("E1202547.2")
        assert abs(r - (120 + 25/60 + 47.2/3600)) < 1e-6

    def test_lon_without_decimal(self):
        r = parse_aip_lon("E1203454")
        assert abs(r - (120 + 34/60 + 54/3600)) < 1e-6

    def test_lat_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_aip_lat("S301733.4")

    def test_lon_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_aip_lon("W1202547.2")

    def test_try_lat_none_on_failure(self):
        assert try_parse_aip_lat("garbage") is None

    def test_try_lon_none_on_failure(self):
        assert try_parse_aip_lon("garbage") is None

    def test_lat_minute_out_of_range(self):
        with pytest.raises(ValueError):
            parse_aip_lat("N306033.4")

    def test_lat_second_out_of_range(self):
        with pytest.raises(ValueError):
            parse_aip_lat("N301760.0")


def _block(text, icao="ZSHC", page=1):
    return TextBlock(page=page, text=text, source_file="test.txt", airport_icao=icao)

def _parse(text, icao="ZSHC"):
    return parse_blocks_aip([_block(text, icao)])


def _table_row(cells, page=1):
    return {
        "page": page,
        "airport_icao": "ZGKL",
        "source_file": "test.pdf",
        "cells": cells,
    }


class TestAipTableRows:
    def test_merges_split_data_row_with_following_id_only_row(self):
        group = [
            _table_row(["", "\u5c71", "", "\u5c71", "245/5163", "330", ""]),
            _table_row(["", "019", "", "", "", "", ""]),
        ]

        obs, fails = parse_aip_table_rows([group])

        assert fails == []
        assert len(obs) == 1
        assert obs[0].obstacle_id == "019"
        assert obs[0].name == "\u5c71"
        assert obs[0].mag_bearing_deg == 245.0
        assert obs[0].distance_m == 5163.0
        assert obs[0].elevation_m == 330.0

    def test_duplicate_id_only_row_after_complete_row_is_ignored(self):
        group = [
            _table_row(["\u5c71\n049", "", "", "\u5c71", "162/30900", "685", ""]),
            _table_row(["", "049", "", "", "", "", ""]),
            _table_row(["", "\u5c71", "", "\u5c71", "163/30797", "685", ""]),
            _table_row(["", "050", "", "", "", "", ""]),
        ]

        obs, fails = parse_aip_table_rows([group])

        assert fails == []
        assert [o.obstacle_id for o in obs] == ["049", "050"]
        assert obs[0].distance_m == 30900.0
        assert obs[1].distance_m == 30797.0


STANDARD_5LINE = 'N301733.4\n青龙山\n山 E1202547.2 142.0\n001\n002/7010\n'
OVERFLOW = '楼顶炮台（雷山村 N301533.1\n二组） 建筑 E1202701.1 24.1 RWY06起飞航径区重要障碍物\n005 031/3630\n'
WATERMARK = 'C 机坪塔台甚高频 N301426.8\nA RWY25 LNAV/VNAV最后进近控\nA 地空通信台 天线 E1202627.9 50.8\nA 009 033/1406\n制障碍物\n'
PARTIAL = '铁塔\n建筑 E1202547.2 50.0\n010\n090/2000\n'
MULTI = 'N301733.4\n青龙山\n山 E1202547.2 142.0\n001\n002/7010\nN301526.7\n豪利达实业\n建筑 E1202651.2 20.6 RWY06起飞航径区重要障碍物\n002\n028/3342\nN301526.8\n艾德乐卫浴2\n建筑 E1202656.8 22.9 RWY06起飞航径区重要障碍物\n003\n030/3405\n'


class TestStandardFormat:
    def test_returns_one_obstacle(self):
        obs, fails = _parse(STANDARD_5LINE)
        assert len(obs) == 1, f"fails={[f.reason for f in fails]}"

    def test_obstacle_id(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].obstacle_id == "001"

    def test_name_contains_chinese(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert "青龙山" in obs[0].name

    def test_latitude(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].latitude is not None
        assert abs(obs[0].latitude - (30 + 17/60 + 33.4/3600)) < 1e-5

    def test_longitude(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].longitude is not None
        assert abs(obs[0].longitude - (120 + 25/60 + 47.2/3600)) < 1e-5

    def test_elevation_no_unit(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].elevation_m == 142.0

    def test_mag_bearing(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].mag_bearing_deg == 2.0

    def test_distance_m(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].distance_m == 7010.0

    def test_bearing_deg_is_none(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].bearing_deg is None

    def test_raw_text_not_empty(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].raw_text != ""

    def test_airport_icao(self):
        obs, _ = _parse(STANDARD_5LINE, icao="ZSHC")
        assert obs[0].airport_icao == "ZSHC"


class TestNameOverflowVariant:
    def test_returns_obstacle(self):
        obs, fails = _parse(OVERFLOW)
        assert len(obs) == 1, f"fails={[f.reason for f in fails]}"

    def test_obstacle_id(self):
        obs, _ = _parse(OVERFLOW)
        assert obs[0].obstacle_id == "005"

    def test_mag_bearing_from_anchor(self):
        obs, _ = _parse(OVERFLOW)
        assert obs[0].mag_bearing_deg == 31.0
        assert obs[0].distance_m == 3630.0

    def test_elevation(self):
        obs, _ = _parse(OVERFLOW)
        assert obs[0].elevation_m == 24.1

    def test_latitude_extracted(self):
        obs, _ = _parse(OVERFLOW)
        assert obs[0].latitude is not None


class TestWatermarkVariant:
    def test_returns_obstacle(self):
        obs, fails = _parse(WATERMARK)
        assert len(obs) == 1, f"fails={[f.reason for f in fails]}"

    def test_obstacle_id(self):
        obs, _ = _parse(WATERMARK)
        assert obs[0].obstacle_id == "009"

    def test_mag_bearing_and_dist(self):
        obs, _ = _parse(WATERMARK)
        assert obs[0].mag_bearing_deg == 33.0
        assert obs[0].distance_m == 1406.0

    def test_elevation(self):
        obs, _ = _parse(WATERMARK)
        assert obs[0].elevation_m == 50.8


class TestConfidenceScore:
    def test_full_score(self):
        # 有方位距离 + 经纬度 + 高度 -> 1.0
        obs, _ = _parse(STANDARD_5LINE)
        assert obs[0].confidence_score >= 0.99

    def test_partial_score_no_latlon(self):
        # 缺经纬度不再降低可信度；方位距离 + 高度即可视为高可信
        obs, fails = _parse(PARTIAL)
        assert len(obs) == 1, f"应成功解析，fails={[f.reason for f in fails]}"
        assert obs[0].confidence_score >= 0.99

    def test_score_range(self):
        obs, _ = _parse(STANDARD_5LINE)
        assert 0.0 <= obs[0].confidence_score <= 1.0


class TestMultipleRecords:
    def test_three_records_parsed(self):
        obs, fails = _parse(MULTI)
        assert len(obs) == 3, f"期望3条，实际{len(obs)}条，失败：{[f.reason for f in fails]}"

    def test_ids_sequential(self):
        obs, _ = _parse(MULTI)
        ids = [o.obstacle_id for o in obs]
        assert "001" in ids
        assert "002" in ids
        assert "003" in ids


@_SKIP_IF_NO_PDF
class TestRealPdf:
    def test_page1_at_least_5_records(self):
        import pdfplumber
        with pdfplumber.open(str(_PDF_PATH)) as pdf:
            text = pdf.pages[0].extract_text() or ""
        block = _block(text, icao="ZSHC", page=1)
        obs, fails = parse_blocks_aip([block])
        assert len(obs) >= 5, f"第1页只解析到 {len(obs)} 条，失败 {len(fails)} 条"

    def test_all_pages_at_least_100_records(self):
        import pdfplumber
        from aip_obstacle.parsers.pdf_parser import parse_pdf
        blocks = parse_pdf(_PDF_PATH)
        obs, fails = parse_blocks_aip(blocks)
        assert len(obs) >= 100, f"全文只解析到 {len(obs)} 条，失败 {len(fails)} 条"

    def test_all_have_mag_bearing(self):
        import pdfplumber
        from aip_obstacle.parsers.pdf_parser import parse_pdf
        blocks = parse_pdf(_PDF_PATH)
        obs, _ = parse_blocks_aip(blocks)
        # 方位距离是必须字段，所有成功记录都应有值
        missing = [o.obstacle_id for o in obs if o.mag_bearing_deg is None]
        assert len(missing) == 0, f"以下记录缺少磁方位：{missing[:10]}"

    def test_elevation_mostly_present(self):
        import pdfplumber
        from aip_obstacle.parsers.pdf_parser import parse_pdf
        blocks = parse_pdf(_PDF_PATH)
        obs, _ = parse_blocks_aip(blocks)
        # 高度是附加字段，允许少量缺失（远距离区域可能无高度）
        missing = [o.obstacle_id for o in obs if o.elevation_m is None]
        assert len(missing) <= 10, f"缺少高度的记录过多：{len(missing)} 条"

    def test_confidence_scores_reasonable(self):
        import pdfplumber
        from aip_obstacle.parsers.pdf_parser import parse_pdf
        blocks = parse_pdf(_PDF_PATH)
        obs, _ = parse_blocks_aip(blocks)
        low = [o.obstacle_id for o in obs if o.confidence_score < 0.5]
        assert len(low) == 0, f"以下记录置信度过低：{low[:10]}"


@_SKIP_IF_NO_GUILIN
def test_guilin_pdf_keeps_split_id_rows():
    from aip_obstacle.pipeline import parse_file

    result = parse_file(_GUILIN_PDF)
    ids = {obs.obstacle_id for obs in result.obstacles}
    expected_missing_before_fix = {
        "019", "036", "038", "039", "042", "044", "046", "047", "050", "052",
        "053", "055", "057", "059", "070", "073", "076", "079", "081", "095",
    }

    assert result.stats.total_success == 95
    assert expected_missing_before_fix <= ids
    assert result.stats.total_failed == 0
