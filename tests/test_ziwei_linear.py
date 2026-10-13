"""真实数据下的星名布局、独立坐标含义和 Linear 可读性检查。"""

import copy
import hashlib
import io
import json

import pytest
from PIL import Image

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_correspondence import build_correspondence
from local_core.ziwei_linear import HEIGHT, SKY_ORIGIN, WIDTH, render_ziwei_linear
from local_core.ziwei_linear_theme import BG, CJK, INK, INTER, MUTED
from local_core.ziwei_names import CENTER, RADIUS, segment_hits_box


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine()
    yield SkyChartEngine(core)
    core.close()


@pytest.mark.parametrize(
    "content",
    [
        "/紫微星图 北京 20261012200000",
        "/紫微星图 -33.8688,151.2093 20261012120000",
        "/紫微星图 89,0 20261012000000 tz=UTC",
        "/紫微星图 0,0 20261012080000 tz=UTC",
        "/紫微星图 北京 20200523000000",
    ],
)
def test_named_points_and_traditional_positions_are_separate_without_overlap(sky, content):
    data = compute_ziwei(sky, content)
    before = copy.deepcopy(data)
    comparison = build_correspondence(data)
    png, layouts = render_ziwei_linear(data, comparison)
    assert data == before
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG" and image.size == (WIDTH, HEIGHT)
        assert image.getpixel((0, 0)) == (10, 10, 11)
    left = {r["key"]: r for r in layouts["traditional"] if r["kind"] == "shared_star"}
    right = {r["key"]: r for r in layouts["real_names"]}
    rows = {r["key"]: r for r in comparison["rows"]}
    objects = {o["key"]: o for o in data["single_chart"]["objects"]}
    assert set(left) == set(right) == set(objects) and len(right) == 17
    assert comparison["real_frame"] == "topocentric_horizontal_no_refraction"
    assert comparison["association"] == "same_name_and_fixed_number_only"
    for key, obj in objects.items():
        label = right[key]
        assert obj["name"] in label["primary"] and rows[key]["target"] in label["secondary"]
        assert label["number"] == left[key]["number"]
        assert left[key]["branch"] == rows[key]["traditional_branch"]
        assert label["observer_xy"] == obj["single_xy"]
        assert label["point_px"] == pytest.approx(
            [
                SKY_ORIGIN[0] + CENTER + obj["single_xy"][0] * RADIUS,
                SKY_ORIGIN[1] + CENTER + obj["single_xy"][1] * RADIUS,
            ]
        )
        assert "same_branch" not in rows[key] and "real_research_branch" not in rows[key]
        assert rows[key]["altitude_deg"] == obj["altitude_deg"]
        assert rows[key]["azimuth_deg"] == obj["azimuth_deg"]
        if label["leader_visible"]:
            assert not any(
                segment_hits_box(*label["leader_line"], other["box"])
                for other in right.values()
                if other["key"] != key
            )
    for labels in layouts.values():
        for index, label in enumerate(labels):
            a = label["box"]
            assert 0 <= a[0] < a[2] <= WIDTH and 0 <= a[1] < a[3] <= HEIGHT
            if "cell_box" in label:
                c = label["cell_box"]
                assert c[0] <= a[0] < a[2] <= c[2] and c[1] <= a[1] < a[3] <= c[3]
            for other in labels[index + 1 :]:
                b = other["box"]
                assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]


def test_correspondence_evidence_categories_are_explicit(sky):
    data = compute_ziwei(sky, "/紫微星图 北京 20261012200000")
    rows = {r["name"]: r for r in build_correspondence(data)["rows"]}
    assert rows["太阳"]["mapping"]["class"] == rows["太阴"]["mapping"]["class"] == "entity"
    for name in ["贪狼", "巨门", "禄存", "文曲", "廉贞", "武曲", "破军"]:
        assert rows[name]["mapping"]["class"] == "historical_alias"
        assert rows[name]["mapping"]["source"].startswith("https://hk.space.museum/")
    for name in ["紫微", "天机", "天同", "天府", "天相", "天梁", "七杀", "左辅"]:
        assert rows[name]["mapping"]["class"] == "display_convention"
    assert rows["太阳"]["magnitude_estimated"] and not rows["武曲"]["magnitude_estimated"]


def test_font_and_text_contrast_fit_linear_reference():
    record = json.loads(INTER.with_name("linear_provenance.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(INTER.read_bytes()).hexdigest() == record["output_sha256"]
    assert (
        hashlib.sha256(INTER.with_name("LINEAR_LICENSE.txt").read_bytes()).hexdigest()
        == (record["license_sha256"])
    )
    assert CJK.is_file()

    def luminance(color):
        values = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))

    for color in (INK, MUTED):
        assert (luminance(color) + 0.05) / (luminance(BG) + 0.05) >= 4.5
