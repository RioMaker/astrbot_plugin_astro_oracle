"""密集标签本宫约束及无法容纳时的显式回退。"""

import hashlib
import json

import numpy as np
from PIL import Image, ImageDraw

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_label_layout import choose_object_label
from local_core.ziwei_palace_display import prepare_display_layer
from local_core.ziwei_theme import FONT


def test_no_home_space_uses_explicit_leader_without_reassigning_object():
    core = PlanetEngine()
    try:
        data = compute_ziwei(SkyChartEngine(core), "/xt 北京 20261012200000")
        obj = data["single_chart"]["objects"][0]
        before = dict(obj)
        # 所有候选像素标为圆外，模拟本宫没有可用区域。
        blocked_regions = np.full((1160, 1160), -1, dtype=np.int8)
        draw = ImageDraw.Draw(Image.new("RGB", (2320, 2320)))
        label = choose_object_label(
            draw, obj, prepare_display_layer(data["palace_layer"]), blocked_regions, []
        )
        assert label["placement"] == "leader_fallback"
        assert label["fallback_reason"] == "home_region_full"
        assert label["branch"] == obj["research_branch"]
        assert obj == before
    finally:
        core.close()


def test_bundled_serif_matches_recorded_font_snapshot():
    record = json.loads(FONT.with_name("serif_provenance.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(FONT.read_bytes()).hexdigest() == record["output_sha256"]
    assert FONT.with_name("SERIF_LICENSE.txt").is_file()
