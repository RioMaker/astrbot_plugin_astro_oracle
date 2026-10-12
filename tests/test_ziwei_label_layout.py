"""真实星点编号身份、原坐标和归属不因说明布局改变。"""

import hashlib
import json

from PIL import Image, ImageDraw

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_label_layout import choose_number_marker, object_number
from local_core.ziwei_theme import FONT


def test_number_marker_preserves_identity_position_and_owner():
    core = PlanetEngine()
    try:
        data = compute_ziwei(SkyChartEngine(core), "/xt 北京 20261012200000")
        draw = ImageDraw.Draw(Image.new("RGB", (2320, 2320)))
        for obj in data["single_chart"]["objects"]:
            before = dict(obj)
            label = choose_number_marker(draw, obj, [])
            assert label["number"] == object_number(obj)
            assert label["point_xy"] == obj["display_xy"]
            assert label["branch"] == obj["research_branch"]
            assert obj == before
        assert {object_number(o) for o in data["single_chart"]["objects"]} == {
            f"{i:02d}" for i in range(1, 18)
        }
    finally:
        core.close()


def test_bundled_serif_matches_recorded_font_snapshot():
    record = json.loads(FONT.with_name("serif_provenance.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(FONT.read_bytes()).hexdigest() == record["output_sha256"]
    assert FONT.with_name("SERIF_LICENSE.txt").is_file()
