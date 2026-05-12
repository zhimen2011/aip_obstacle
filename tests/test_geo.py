"""测试：坐标转换与单位换算（utils/geo.py）。"""

import pytest
from aip_obstacle.utils.geo import (
    dms_to_decimal,
    feet_to_meter,
    meter_to_feet,
    distance_to_meter,
    height_to_meter,
    try_dms_to_decimal,
)


class TestDmsToDecimal:
    def test_compact_north(self):
        # 39°48'12"N -> 39 + 48/60 + 12/3600
        result = dms_to_decimal("394812N")
        assert abs(result - (39 + 48 / 60 + 12 / 3600)) < 1e-6

    def test_compact_east(self):
        result = dms_to_decimal("1161800E")
        assert abs(result - (116 + 18 / 60 + 0 / 3600)) < 1e-6

    def test_south_negative(self):
        result = dms_to_decimal("394812S")
        assert result < 0

    def test_west_negative(self):
        result = dms_to_decimal("1161800W")
        assert result < 0

    def test_symbolic_format(self):
        result = dms_to_decimal("39°48'12\"N")
        assert abs(result - (39 + 48 / 60 + 12 / 3600)) < 1e-6

    def test_with_decimal_seconds(self):
        result = dms_to_decimal("394812.3N")
        assert abs(result - (39 + 48 / 60 + 12.3 / 3600)) < 1e-6

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            dms_to_decimal("not_a_coord")

    def test_minute_out_of_range(self):
        with pytest.raises(ValueError):
            dms_to_decimal("396012N")  # 60 分无效

    def test_try_dms_returns_none_on_failure(self):
        assert try_dms_to_decimal("garbage") is None


class TestUnitConversion:
    def test_feet_to_meter(self):
        assert abs(feet_to_meter(1000) - 304.8) < 0.1

    def test_meter_to_feet(self):
        assert abs(meter_to_feet(304.8) - 1000) < 0.1

    def test_distance_m(self):
        assert distance_to_meter(500, "m") == 500.0

    def test_distance_km(self):
        assert distance_to_meter(1, "km") == 1000.0

    def test_distance_nm(self):
        assert abs(distance_to_meter(1, "NM") - 1852.0) < 0.01

    def test_distance_unknown_unit(self):
        with pytest.raises(ValueError):
            distance_to_meter(1, "mile")

    def test_height_ft(self):
        assert abs(height_to_meter(1000, "ft") - 304.8) < 0.1

    def test_height_m(self):
        assert height_to_meter(100, "m") == 100.0

    def test_height_unknown_unit(self):
        with pytest.raises(ValueError):
            height_to_meter(100, "yard")
