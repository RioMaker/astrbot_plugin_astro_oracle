"""宫区显示回归：以真实 Skyfield 高度和原始宫界为独立参照。"""

import copy
import math

import pytest

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_palace_display import (
    altitude_at_xy,
    horizon_curves,
    prepare_display_layer,
    right_ascension_at_xy,
    sector_ids_at_xy,
)
from local_core.ziwei_palaces import BRANCHES, locate_sector, project_north_pole


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine()
    yield SkyChartEngine(core)
    core.close()


@pytest.mark.parametrize(
    "command",
    [
        "/xt 北京 20261012200000",
        "/xt -33.8688,151.2093 20010101010000",
        "/xt 0,0 20261012080000 tz=UTC",
        "/xt 90,0 20261012000000 tz=UTC",
        "/xt -90,0 20261012000000 tz=UTC",
    ],
)
def test_display_horizon_matches_real_topocentric_altitudes(sky, command):
    data = compute_ziwei(sky, command)
    layer = data["palace_layer"]
    assert data["single_chart"]["center"] == "north_celestial_pole"
    assert data["single_chart"]["display_projection"]["objects_xy_field"] == "display_xy"
    context = layer["projection_context"]
    for obj in data["single_chart"]["objects"]:
        x, y = obj["display_xy"]
        assert float(altitude_at_xy(x, y, context)) == pytest.approx(obj["altitude_deg"], abs=1e-8)
        assert float(right_ascension_at_xy(x, y)) == pytest.approx(obj["ra_date_deg"])
        assert math.hypot(x, y) == pytest.approx((90 - obj["dec_date_deg"]) / 180)
        assert int(sector_ids_at_xy(x, y, layer)) == BRANCHES.index(obj["research_branch"])
    curves = horizon_curves(layer)
    assert curves
    for curve in curves:
        assert len(curve) > 1
        for x, y in curve:
            assert abs(float(altitude_at_xy(x, y, context))) < 2e-6
        assert all(math.dist(a, b) <= 0.15 for a, b in zip(curve, curve[1:]))


def test_sector_map_wraps_at_zero_and_display_keeps_research_data_unchanged(sky):
    layer = compute_ziwei(sky, "/xt 北京 20261012200000")["palace_layer"]
    original = copy.deepcopy(layer)
    display = prepare_display_layer(layer)
    assert layer == original
    for sector in display["sectors"]:
        assert sector["curves"] == [[[0, 0], project_north_pole(sector["start_ra_deg"], -90)]]
        assert sector["name"] == next(
            s["name"] for s in original["sectors"] if s["branch"] == sector["branch"]
        )
    # 稠密采样与计算层逐区搜索对照，包含 0h 接缝与圆外裁剪。
    for ra in (0, 0.001, 359.999, *range(360)):
        x, y = project_north_pole(ra, -30)
        expected = locate_sector(ra, original["sectors"])["branch"]
        assert int(sector_ids_at_xy(x, y, display)) == BRANCHES.index(expected)
    assert int(sector_ids_at_xy(1.01, 0, display)) == -1
