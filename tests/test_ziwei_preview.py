import copy
import io
import math
from datetime import datetime, timezone

import pytest
from PIL import Image

from local_core.bot_commands import ChartSettings
from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import (
    MAJOR_ORDER,
    compute_ziwei,
    parse_preview_request,
    project_all_sky,
)
from local_core.ziwei_palace_display import box_inside_palace, palace_region_map
from local_core.ziwei_palace_ledger import HEIGHT, WIDTH
from local_core.ziwei_single_renderer import render_ziwei_png


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine()
    yield SkyChartEngine(core)
    core.close()


@pytest.mark.parametrize("prefix", ["/星图", "/xingtu", "/xt", "/star", "/STAR"])
def test_full_command_uses_existing_parameter_contract(prefix):
    request = parse_preview_request(f" {prefix}\t30.25°N 120.5°E 200010100100 ")
    assert request.time_text == "200010100100"
    assert request.place_text == "30.25°N 120.5°E"
    assert parse_preview_request(prefix).action == "now"


@pytest.mark.parametrize("content", ["/星图 help", "/xt 20261301", "/star 30.25°N"])
def test_preview_rejects_help_and_bad_input(content):
    with pytest.raises(ValueError):
        parse_preview_request(content)


def test_selected_objects_are_complete_unique_and_match_existing_real_coordinates(sky):
    data = compute_ziwei(sky, "/星图 北京 20261012200000", ChartSettings(magnitude_limit=-2))
    plain = sky.compute(data["epoch_utc"], data["site"], data["timezone"], magnitude_limit=8)
    reference = {s["hip"]: s for scene in plain["hemispheres"].values() for s in scene["stars"]}
    objects = [obj for scene in data["hemispheres"].values() for obj in scene["objects"]]
    assert len(objects) == len({obj["key"] for obj in objects}) == 17
    assert {obj["name"] for obj in objects if obj["major"]} == set(MAJOR_ORDER)
    assert {obj["name"] for obj in objects if not obj["major"]} == {"禄存", "文曲", "左辅"}
    assert {obj["kind"] for obj in objects} == {"star", "sun", "moon"}
    for hemisphere, scene in data["hemispheres"].items():
        for obj in scene["objects"]:
            assert (obj["altitude_deg"] >= 0) == (hemisphere == "upper")
            assert math.hypot(*obj["xy"]) <= 1 + 1e-10
            if obj["kind"] == "star":
                old = reference[obj["hip"]]
                assert obj["magnitude"] == old["magnitude"]
                assert obj["xy"] == pytest.approx(old["xy"], abs=1e-12)
                assert obj["altitude_deg"] == old["altitude_deg"]
            else:
                assert math.isfinite(obj["magnitude"])
                assert "估算" in obj["magnitude_quality"]
                assert obj["naif_id"] == (10 if obj["kind"] == "sun" else 301)
        for group in scene["constellations"]:
            assert all(math.hypot(*xy) <= 1 + 1e-10 for line in group["lines"] for xy in line)
    sun = next(obj for obj in objects if obj["key"] == "sun")
    assert sun["altitude_deg"] == pytest.approx(plain["sun_altitude_deg"], abs=1e-12)


@pytest.mark.parametrize(
    "command",
    [
        "/星图 北京 20261012200000",
        "/xt 北京 200010100100",
        "/star -33.8688,151.2093 20261012120000",
        "/xingtu 0,0 20261012080000 tz=UTC",
        "/xt 89,0 20261012000000 tz=UTC",
        "/xt -90,0 20261012000000 tz=UTC",
        "/xt 北京 20010124000000",
        "/xt 北京 18500101000000",
    ],
)
def test_real_previews_keep_all_labels_in_bounds_without_overlap(sky, command):
    data = compute_ziwei(sky, command)
    original = copy.deepcopy(data)
    png, layouts = render_ziwei_png(data)
    assert data == original
    regions = palace_region_map(data["palace_layer"])
    objects = {o["key"]: o for o in data["single_chart"]["objects"]}
    palaces = {f"palace:{s['branch']}" for s in data["palace_layer"]["sectors"]}
    symbols = {s["key"]: s for s in data["palace_layer"]["symbolic_malefics"]}
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG" and image.size == (WIDTH, HEIGHT)
    assert {label["key"] for label in layouts["single"]} == set(objects) | palaces
    assert {label["key"] for label in layouts["palace_ledger"]} == set(objects) | palaces | set(
        symbols
    )
    marker_numbers = {}
    for label in layouts["single"]:
        box = label["box"]
        assert 0 <= box[0] < box[2] <= 1160 and 0 <= box[1] < box[3] <= 1160
        if label["kind"] == "palace":
            assert box_inside_palace(box, label["branch"], regions)
        else:
            obj = objects[label["key"]]
            assert label["kind"] == "point_number"
            assert label["point_xy"] == obj["display_xy"]
            assert label["branch"] == obj["research_branch"]
            assert math.dist(*label["leader_line"]) <= 84
            marker_numbers[label["key"]] = label["number"]
    assert len(set(marker_numbers.values())) == 17
    for label in layouts["palace_ledger"]:
        box, card = label["box"], label["card_box"]
        assert card[0] <= box[0] < box[2] <= card[2] <= WIDTH
        assert card[1] <= box[1] < box[3] <= card[3] <= HEIGHT
        assert label["placement"] == "palace_card"
        if label["kind"] == "object":
            assert label["branch"] == objects[label["key"]]["research_branch"]
            assert label["number"] == marker_numbers[label["key"]]
        elif label["kind"] == "symbolic":
            assert label["branch"] == symbols[label["key"]]["branch"]
    for labels in layouts.values():
        for index, label in enumerate(labels):
            box = label["box"]
            for other in labels[index + 1 :]:
                b = other["box"]
                assert box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]


def test_existing_defaults_and_southern_hemisphere_remain_physical(sky):
    now = datetime(2026, 10, 12, 10, 12, 13, tzinfo=timezone.utc)
    current = compute_ziwei(sky, "/星图", now=now)
    assert current["epoch_utc"] == now.isoformat()
    compact = compute_ziwei(sky, "/xt 北京 20010101")
    exact = compute_ziwei(sky, "/xt 20010101080000 北京")
    assert compact["hemispheres"] == exact["hemispheres"]
    south = compute_ziwei(sky, "/star -33.8688,151.2093 20261012200000")
    polaris = next(obj for obj in south["hemispheres"]["lower"]["objects"] if obj["name"] == "紫微")
    assert abs(polaris["altitude_deg"] - south["site"]["latitude"]) < 1


def test_out_of_ephemeris_range_is_rejected(sky):
    with pytest.raises(ValueError, match="历表"):
        compute_ziwei(sky, "/xt 北京 17000101")


def test_single_chart_projection_retains_real_horizon_and_directions(sky):
    assert project_all_sky(90, 75) == pytest.approx([0, 0])
    assert project_all_sky(0, 0) == pytest.approx([0, -0.5])
    assert project_all_sky(0, 90) == pytest.approx([-0.5, 0])
    assert math.hypot(*project_all_sky(-90, 75)) == pytest.approx(1)
    data = compute_ziwei(sky, "/xt 北京 20261012200000")
    for obj in data["single_chart"]["objects"]:
        radius = math.hypot(*obj["single_xy"])
        assert 0 <= radius <= 1
        assert (radius <= 0.5) == (obj["altitude_deg"] >= 0)
        assert obj["display_state"] == ("bright" if obj["altitude_deg"] >= 0 else "dim")
