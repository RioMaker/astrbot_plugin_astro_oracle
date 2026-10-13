"""指令图的真实点保真、传统宫内说明与关联区域文字边界。"""

import copy
import io
from datetime import datetime, timezone

import numpy as np
import pytest
from PIL import Image

from local_core.bot_commands import ChartSettings, parse_request
from local_core.bundled_resources import BUNDLE_DIR
from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_association import region_map
from local_core.ziwei_atlas import HEIGHT, SKY_ORIGIN, WIDTH, render_ziwei_atlas
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_correspondence import build_correspondence
from local_core.ziwei_linear import generate_ziwei_png, named_rows
from local_core.ziwei_names import CENTER, PANEL, RADIUS, segment_hits_box
from local_core.ziwei_palaces import BRANCHES


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine(BUNDLE_DIR)
    yield SkyChartEngine(core)
    core.close()


def _disjoint(a, b):
    return a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]


@pytest.mark.parametrize(
    "content",
    [
        "/紫薇星图 北京 20261012200000",
        "/紫微星图 -33.8688,151.2093 20261012120000",
        "/紫薇星图 89,0 20261012000000 tz=UTC",
        "/紫薇星图 0,0 20261012080000 tz=UTC",
        "/紫薇星图 北京 20200523000000",
        "/紫薇星图 北京 19900501060000",
    ],
)
def test_true_points_palace_ownership_and_region_names(sky, content):
    data = compute_ziwei(sky, content)
    before = copy.deepcopy(data)
    comparison = build_correspondence(data)
    png, layout = render_ziwei_atlas(data, comparison)
    assert data == before
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (WIDTH, HEIGHT) and image.format == "PNG"
    points = {r["key"]: r for r in layout["real_names"]}
    traditional = {r["key"]: r for r in layout["traditional"] if r["kind"] == "shared_star"}
    assert set(points) == set(traditional) and len(points) == 17
    assert len([r for r in layout["traditional"] if r["kind"] in {"shared_star", "symbolic"}]) == 25
    for row in comparison["rows"]:
        label = points[row["key"]]
        assert label["number"] == traditional[row["key"]]["number"]
        assert traditional[row["key"]]["branch"] == row["traditional_branch"]
        assert label["observer_xy"] == row["observer_xy"]
        assert label["point_px"] == pytest.approx(
            [SKY_ORIGIN[i] + CENTER + row["observer_xy"][i] * RADIUS for i in range(2)]
        )
    for group in (
        layout["traditional"],
        layout["links"],
        [*points.values(), *layout["region_names"]],
    ):
        for index, label in enumerate(group):
            b = label["box"]
            assert 0 <= b[0] < b[2] <= WIDTH and 0 <= b[1] < b[3] <= HEIGHT
            if "cell_box" in label:
                c = label["cell_box"]
                assert c[0] <= b[0] < b[2] <= c[2] and c[1] <= b[1] < b[3] <= c[3]
            assert all(_disjoint(b, other["box"]) for other in group[index + 1 :])
    regions = region_map(named_rows(comparison), PANEL, CENTER, RADIUS)
    for zone in layout["region_names"]:
        x1, y1, x2, y2 = [int(v - SKY_ORIGIN[i % 2]) for i, v in enumerate(zone["box"])]
        assert np.all(regions[y1 : y2 + 1, x1 : x2 + 1] == BRANCHES.index(zone["branch"]))
    for label in points.values():
        if label["leader_visible"]:
            assert not any(
                segment_hits_box(*label["leader_line"], other["box"])
                for other in [*points.values(), *layout["region_names"]]
                if other is not label
            )
    assert "表达" in layout["association"]["meaning"]


def test_command_renderer_returns_same_actual_png_as_preview(sky):
    request = parse_request("北京 20261012200000")
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    data = compute_ziwei(sky, request, ChartSettings(), now)
    png, _ = render_ziwei_atlas(data, build_correspondence(data))
    assert generate_ziwei_png(sky, request, ChartSettings(), now) == png
