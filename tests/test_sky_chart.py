import json
import math

import numpy as np
import pytest

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine, clipped_arc, direction, project, validate_site


@pytest.mark.parametrize("hemisphere,pole", [("upper", 90), ("lower", -90)])
def test_projection_poles_horizon_and_cardinal_directions(hemisphere, pole):
    np.testing.assert_allclose(project(pole, 75, hemisphere), [0, 0], atol=1e-12)
    np.testing.assert_allclose(project(0, 0, hemisphere), [0, -1], atol=1e-12)
    np.testing.assert_allclose(project(0, 180, hemisphere), [0, 1], atol=1e-12)
    assert project(0, 90, hemisphere)[0] == pytest.approx(-1 if hemisphere == "upper" else 1)


def test_constellation_horizon_clip_avoids_false_chord():
    below1, below2 = direction(-30, 0), direction(-30, 160)
    assert clipped_arc(below1, below2, "upper") == []
    first, second = direction(25, 20), direction(-35, 50)
    upper = clipped_arc(first, second, "upper")
    lower = clipped_arc(first, second, "lower")
    assert len(upper) == len(lower) == 9
    assert np.linalg.norm(upper[-1]) == pytest.approx(1)
    assert np.linalg.norm(lower[0]) == pytest.approx(1)
    assert all(np.linalg.norm(point) <= 1 + 1e-12 for point in upper + lower)


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine()
    result = SkyChartEngine(core)
    yield result
    core.close()


def test_real_sky_is_a_complete_disjoint_hemisphere_partition(sky):
    result = sky.compute(
        "2026-10-08T16:00:00+00:00", {"latitude": 31.22222, "longitude": 121.45806}
    )
    halves = result["hemispheres"]
    upper = {star["hip"] for star in halves["upper"]["stars"]}
    lower = {star["hip"] for star in halves["lower"]["stars"]}
    assert not upper & lower
    assert len(upper | lower) == int(np.count_nonzero(sky.magnitudes <= 6))
    assert 4500 < len(upper | lower) < 6500
    planets = [planet for scene in halves.values() for planet in scene["planets"]]
    assert len(planets) == 7 and len({p["key"] for p in planets}) == 7
    assert "earth" not in {p["key"] for p in planets}
    for hemisphere, scene in halves.items():
        for obj in scene["stars"] + scene["planets"] + scene["references"]:
            assert (obj["altitude_deg"] >= 0) == (hemisphere == "upper")
            assert math.hypot(*obj["xy"]) <= 1 + 1e-10
        for constellation in scene["constellations"]:
            assert all(math.hypot(*p) <= 1 + 1e-10 for line in constellation["lines"] for p in line)
    polaris = next(star for star in halves["upper"]["stars"] if star["hip"] == 11767)
    assert abs(polaris["altitude_deg"] - 31.22222) < 1
    json.dumps(result, allow_nan=False)


def test_birthplace_and_time_change_actual_sky(sky):
    epoch = "2026-10-08T16:00:00+00:00"
    north = sky.compute(epoch, {"latitude": 31.22222, "longitude": 121.45806})
    south = sky.compute(epoch, {"latitude": -33.8688, "longitude": 151.2093})
    polaris = next(star for star in south["hemispheres"]["lower"]["stars"] if star["hip"] == 11767)
    assert polaris["altitude_deg"] < 0
    later = sky.compute("2026-10-08T22:00:00+00:00", north["site"])
    assert north["sun_altitude_deg"] != later["sun_altitude_deg"]
    assert {p["key"] for p in north["hemispheres"]["upper"]["planets"]} != {
        p["key"] for p in later["hemispheres"]["upper"]["planets"]
    }


def test_real_place_search_supports_chinese_and_timezone(sky):
    shanghai = sky.places.search("上海")[0]
    assert shanghai["id"] == 1796236 and shanghai["country"] == "CN"
    assert shanghai["timezone"] == "Asia/Shanghai"
    assert 30 < shanghai["latitude"] < 32 and 120 < shanghai["longitude"] < 122
    new_york = sky.places.search("New York")[0]
    assert new_york["timezone"] == "America/New_York"


@pytest.mark.parametrize(
    "site",
    [
        None,
        {},
        {"latitude": 91, "longitude": 0},
        {"latitude": 0, "longitude": float("nan")},
        {"latitude": True, "longitude": 0},
    ],
)
def test_invalid_site_is_rejected(site):
    with pytest.raises(ValueError):
        validate_site(site)


def test_sky_requires_exact_aware_time_and_declares_models(sky):
    with pytest.raises(ValueError, match="偏移"):
        sky.compute("2026-10-09T00:00:00", {"latitude": 0, "longitude": 0})
    with pytest.raises(ValueError, match="星等"):
        sky.compute("2026-10-09T00:00:00Z", {"latitude": 0, "longitude": 0}, magnitude_limit=20)
    result = sky.compute(
        "2026-10-09T00:00:00Z", {"latitude": 0, "longitude": 0}, magnitude_limit=-2
    )
    assert not any(scene["stars"] for scene in result["hemispheres"].values())
    assert result["provenance"]["sky_resources"]["credits"]["constellations"].endswith(
        "CC BY-SA 2.0"
    )
