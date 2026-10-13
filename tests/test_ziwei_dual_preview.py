import copy
import io

import pytest
from PIL import Image

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_palace_display import box_inside_palace, palace_region_map
from tools.preview_ziwei_dual import HEIGHT, REAL_ORIGIN, WIDTH, render_dual
from tools.ziwei_rules_research import compare_sky


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine()
    yield SkyChartEngine(core)
    core.close()


@pytest.mark.parametrize(
    "command",
    [
        "/星图 北京 20261012200000",
        "/star -33.8688,151.2093 20261012120000",
        "/xt 北京 20200523000000",
    ],
)
def test_both_views_share_number_identity_and_accurate_independent_ownership(sky, command):
    data = compute_ziwei(sky, command)
    before = copy.deepcopy(data)
    comparison = compare_sky(data)
    png, layouts = render_dual(data, comparison)
    assert data == before
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (WIDTH, HEIGHT) and image.format == "PNG"
    left = {r["key"]: r for r in layouts["traditional"] if r["kind"] == "shared_star"}
    right = {r["key"]: r for r in layouts["real"] if r["kind"] == "point_number"}
    differences = {r["key"]: r for r in layouts["differences"]}
    objects = {o["key"]: o for o in data["single_chart"]["objects"]}
    rows = {r["key"]: r for r in comparison["rows"]}
    assert set(left) == set(right) == set(differences) == set(objects)
    assert len(left) == 17
    assert {r["number"] for r in left.values()} == {f"{i:02d}" for i in range(1, 18)}
    assert len([r for r in layouts["traditional"] if r["kind"] == "symbolic"]) == 8
    for key, obj in objects.items():
        assert left[key]["number"] == right[key]["number"] == differences[key]["number"]
        assert left[key]["branch"] == rows[key]["traditional_branch"]
        assert right[key]["branch"] == obj["research_branch"]
        assert left[key]["same_branch"] == right[key]["same_branch"] == rows[key]["same_branch"]
        assert right[key]["point_xy"] == obj["display_xy"]
        assert right[key]["point_px"] == pytest.approx(
            [
                REAL_ORIGIN[0] + 580 + obj["display_xy"][0] * 492,
                REAL_ORIGIN[1] + 580 + obj["display_xy"][1] * 492,
            ]
        )
    for labels in layouts.values():
        for index, label in enumerate(labels):
            box = label["box"]
            assert 0 <= box[0] < box[2] <= WIDTH and 0 <= box[1] < box[3] <= HEIGHT
            if "cell_box" in label:
                cell = label["cell_box"]
                assert cell[0] <= box[0] < box[2] <= cell[2]
                assert cell[1] <= box[1] < box[3] <= cell[3]
            for other in labels[index + 1 :]:
                b = other["box"]
                assert box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
    real_palaces = {r["branch"]: r["label"] for r in layouts["real"] if r["kind"] == "palace"}
    regions = palace_region_map(data["palace_layer"])
    for label in layouts["real"]:
        if label["kind"] == "palace":
            local_box = [label["box"][i] - REAL_ORIGIN[i % 2] for i in range(4)]
            assert box_inside_palace(local_box, label["branch"], regions)
    for branch, name in comparison["traditional"]["palace_names"].items():
        assert real_palaces[branch].startswith(name)
