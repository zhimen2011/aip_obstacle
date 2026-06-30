"""测试：GUI 障碍物表格颜色规则。"""

from aip_obstacle.models import Obstacle, ParseFailure, ParseResult, ParseStats
from aip_obstacle.ui.main_window import (
    _COLOR_HIGH_RISK,
    _COLOR_RISK,
    _COLOR_USER_MODIFIED,
    _obstacle_row_color,
    _result_rows_for_review,
    _resolve_output_dir,
    _validate_review_rows,
)


def test_user_modified_is_blue_and_has_priority():
    row = {"is_user_modified": 1, "confidence_score": 0.1}

    assert _obstacle_row_color(row) == _COLOR_USER_MODIFIED


def test_string_zero_is_not_treated_as_modified():
    row = {"is_user_modified": "0", "confidence_score": 0.95}

    assert _obstacle_row_color(row) is None


def test_low_confidence_is_high_risk_red():
    row = {"is_user_modified": 0, "confidence_score": 0.49}

    assert _obstacle_row_color(row) == _COLOR_HIGH_RISK


def test_medium_confidence_is_yellow():
    row = {"is_user_modified": 0, "confidence_score": 0.85}

    assert _obstacle_row_color(row) == _COLOR_RISK


def test_high_confidence_has_no_risk_color():
    row = {"is_user_modified": 0, "confidence_score": 0.95}

    assert _obstacle_row_color(row) is None


def test_failed_rows_are_inserted_into_review_order():
    result = ParseResult(
        source_file="aip.pdf",
        file_hash="hash",
        obstacles=[
            Obstacle(
                airport_icao="ZBAA",
                obstacle_id="089",
                name="障碍物89",
                mag_bearing_deg=89.0,
                distance_m=890.0,
                source_page=1,
                raw_text="089 ok",
            ),
            Obstacle(
                airport_icao="ZBAA",
                obstacle_id="091",
                name="障碍物91",
                mag_bearing_deg=91.0,
                distance_m=910.0,
                source_page=1,
                raw_text="091 ok",
            ),
        ],
        failures=[
            ParseFailure(
                airport_icao="ZBAA",
                source_page=1,
                raw_text="090 bad",
                reason="编号 090：缺少方位/距离",
            )
        ],
        stats=ParseStats(total_candidates=3, total_success=2, total_failed=1),
    )

    rows = _result_rows_for_review(result)

    assert [row["obstacle_id"] for row in rows] == ["089", "090", "091"]
    assert rows[1]["_review_status"] == "待补录"


def test_review_validation_blocks_unfilled_placeholder():
    rows = [
        {
            "airport_icao": "ZBAA",
            "obstacle_id": "090",
            "name": "",
            "mag_bearing_deg": None,
            "distance_m": None,
        }
    ]

    errors = _validate_review_rows(rows)

    assert any("缺少名称" in error for error in errors)
    assert any("缺少方位/距离" in error for error in errors)


def test_relative_output_dir_resolves_from_base_dir(tmp_path):
    out_dir = _resolve_output_dir("my-output", tmp_path)

    assert out_dir == tmp_path / "my-output"


def test_empty_output_dir_defaults_to_output(tmp_path):
    out_dir = _resolve_output_dir("", tmp_path)

    assert out_dir == tmp_path / "output"
