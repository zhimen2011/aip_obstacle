"""测试：字段解析（services/field_parser.py）。"""

from aip_obstacle.models import CandidateRow, Obstacle, ParseFailure
from aip_obstacle.services.field_parser import parse_candidate


def _row(text: str, icao: str = "ZBAA", page: int = 1) -> CandidateRow:
    return CandidateRow(raw_text=text, source_page=page, airport_icao=icao)


class TestParseCandidate:
    def test_bearing_and_distance(self):
        row = _row("1 通信塔 045° 2500m")
        result = parse_candidate(row)
        assert isinstance(result, Obstacle)
        assert result.obstacle_id == "1"
        assert result.name == "通信塔"
        assert result.bearing_deg == 45.0
        assert result.distance_m == 2500.0

    def test_latlon(self):
        row = _row("2 烟囱 394812N 1161800E 高度 80m")
        result = parse_candidate(row)
        assert isinstance(result, Obstacle)
        assert result.latitude is not None
        assert result.longitude is not None
        assert abs(result.latitude - (39 + 48 / 60 + 12 / 3600)) < 1e-4

    def test_height_ft_converted(self):
        row = _row("3 大楼 090° 1000m 高度 500ft")
        result = parse_candidate(row)
        assert isinstance(result, Obstacle)
        assert result.height_m is not None
        assert abs(result.height_m - 152.4) < 0.5

    def test_missing_id_returns_failure(self):
        row = _row("通信塔 045° 2500m")  # 无编号
        result = parse_candidate(row)
        assert isinstance(result, ParseFailure)
        assert "编号" in result.reason

    def test_missing_location_returns_failure(self):
        row = _row("1 通信塔 这里没有任何定位信息")
        result = parse_candidate(row)
        assert isinstance(result, ParseFailure)
        assert "定位" in result.reason

    def test_airport_icao_preserved(self):
        row = _row("1 水塔 090° 500m", icao="ZSPD")
        result = parse_candidate(row)
        assert isinstance(result, Obstacle)
        assert result.airport_icao == "ZSPD"

    def test_distance_km(self):
        row = _row("1 铁塔 180° 2.5km")
        result = parse_candidate(row)
        assert isinstance(result, Obstacle)
        assert result.distance_m == 2500.0
        assert result.unit_distance_original == "km"
