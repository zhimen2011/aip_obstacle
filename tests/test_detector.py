"""测试：机场 ICAO 识别 + 候选行识别（services/detector.py）。"""

from aip_obstacle.models import TextBlock
from aip_obstacle.services.detector import detect_candidates


def _make_block(text: str, icao: str = "ZBAA", page: int = 1) -> TextBlock:
    return TextBlock(page=page, text=text, source_file="test.txt", airport_icao=icao)


class TestDetectCandidates:
    def test_basic_candidate_with_height(self):
        text = "1 通信塔 045° 2.5km 高度 120m"
        blocks = [_make_block(text)]
        result = detect_candidates(blocks)
        assert len(result) == 1
        assert result[0].raw_text == text.strip()
        assert result[0].airport_icao == "ZBAA"

    def test_candidate_with_latlon(self):
        text = "2 烟囱 394812N 1161800E 高度 80m"
        blocks = [_make_block(text)]
        result = detect_candidates(blocks)
        assert len(result) == 1

    def test_header_line_filtered(self):
        text = "编号 名称 方位 距离 高度"
        blocks = [_make_block(text)]
        result = detect_candidates(blocks)
        assert len(result) == 0

    def test_separator_line_filtered(self):
        text = "-------------------"
        blocks = [_make_block(text)]
        result = detect_candidates(blocks)
        assert len(result) == 0

    def test_short_line_filtered(self):
        blocks = [_make_block("1 塔")]
        result = detect_candidates(blocks)
        assert len(result) == 0

    def test_multiple_blocks(self):
        b1 = _make_block("1 通信塔 045° 2.5km 高度 120m", icao="ZBAA", page=1)
        b2 = _make_block("2 水塔 090° 1.2km 高度 50m", icao="ZBAA", page=2)
        result = detect_candidates([b1, b2])
        assert len(result) == 2
        assert result[0].source_page == 1
        assert result[1].source_page == 2

    def test_no_id_no_candidate(self):
        # 有高度但没有编号，不应识别为候选
        text = "这是一段普通文字 高度 120m 没有编号"
        blocks = [_make_block(text)]
        result = detect_candidates(blocks)
        assert len(result) == 0
