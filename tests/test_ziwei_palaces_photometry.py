import math
from datetime import datetime

import pytest
from skyfield.api import Star, wgs84

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_palaces import (
    BRANCHES,
    PALACES,
    assign_malefics,
    assign_palaces,
    equatorial_to_horizon,
    locate_sector,
)
from local_core.ziwei_photometry import moon_magnitude, sun_magnitude


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine()
    yield SkyChartEngine(core)
    core.close()


def test_first_lunar_month_zi_hour_starts_at_tiger_and_palaces_run_backwards():
    data = assign_palaces("2001-01-24T00:00:00+08:00")
    assert data["lunar"] == {"year": 2001, "month": 1, "day": 1, "leap": False}
    assert data["life_branch"] == data["body_branch"] == "寅"
    assert data["names"]["寅"] == "命宫"
    assert data["names"]["丑"] == "兄弟"
    assert data["names"]["子"] == "夫妻"
    assert len(data["names"]) == len(set(data["names"].values())) == 12
    assert set(data["names"].values()) == set(PALACES)


def test_late_zi_rolls_across_real_lunar_year_and_date():
    data = assign_palaces("2020-01-24T23:30:00+08:00")
    assert data["lunar"] == {"year": 2020, "month": 1, "day": 1, "leap": False}
    assert data["hour_branch"] == "子" and data["life_branch"] == "寅"
    assert data["astrology_date"].startswith("2020-01-25")


def test_leap_month_split_changes_only_after_fifteenth_day():
    first = assign_palaces("2020-05-23T00:00:00+08:00")
    fifteenth = assign_palaces("2020-06-06T00:00:00+08:00")
    sixteenth = assign_palaces("2020-06-07T00:00:00+08:00")
    assert first["lunar"]["leap"] and first["effective_month"] == 4
    assert fifteenth["lunar"]["day"] == 15 and fifteenth["effective_month"] == 4
    assert sixteenth["lunar"]["day"] == 16 and sixteenth["effective_month"] == 5
    assert first["life_branch"] == "巳" and sixteenth["life_branch"] == "午"
    assert assign_palaces("1899-12-31T12:00:00+08:00")["available"] is False


@pytest.mark.parametrize(
    "site",
    [
        {"latitude": 39.9075, "longitude": 116.39723},
        {"latitude": -33.8688, "longitude": 151.2093},
        {"latitude": 89, "longitude": 0},
    ],
)
def test_boundary_projection_agrees_with_independent_skyfield_altaz(sky, site):
    t = sky.core.ts.from_datetime(datetime.fromisoformat("2026-10-12T12:00:00+00:00"))
    here = (sky.core.earth + wgs84.latlon(site["latitude"], site["longitude"])).at(t)
    for ra, dec in ((0, 0), (110, 35), (300, -20), (359, 85)):
        apparent = here.observe(Star(ra_hours=ra / 15, dec_degrees=dec)).apparent()
        actual_ra, actual_dec, _ = apparent.radec(epoch="date")
        expected_alt, expected_az, _ = apparent.altaz()
        alt, az = equatorial_to_horizon(
            float(actual_ra.hours) * 15,
            float(actual_dec.degrees),
            site["latitude"],
            float(t.gast) * 15 + site["longitude"],
        )
        assert alt == pytest.approx(float(expected_alt.degrees), abs=1e-8)
        delta = (az - float(expected_az.degrees) + 180) % 360 - 180
        assert delta == pytest.approx(0, abs=1e-8)


def test_research_sectors_cover_every_ra_once_and_are_explicitly_not_certified(sky):
    data = compute_ziwei(sky, "/xt 北京 20261012200000")
    layer = data["palace_layer"]
    assert layer["status"] == "research_current_anchor_not_historical_recovery"
    assert layer["assignment"]["life_branch"] == "子"
    assert layer["assignment"]["body_branch"] == "申"
    sectors = layer["sectors"]
    assert len(sectors) == len({s["branch"] for s in sectors}) == 12
    assert sum(s["span_deg"] for s in sectors) == pytest.approx(360)
    assert max(s["span_deg"] for s in sectors) - min(s["span_deg"] for s in sectors) > 5
    for degree in range(360):
        matches = [s for s in sectors if (degree - s["start_ra_deg"]) % 360 < s["span_deg"]]
        assert len(matches) == 1 and locate_sector(degree, sectors) is matches[0]
    for sector in sectors:
        assert all(math.hypot(*xy) <= 1 + 1e-10 for curve in sector["curves"] for xy in curve)
        assert all(
            math.dist(a, b) <= 0.15 for curve in sector["curves"] for a, b in zip(curve, curve[1:])
        )


def test_same_instant_with_different_zone_keeps_sky_and_changes_assignment(sky):
    local = compute_ziwei(sky, "/xt 39.9075,116.39723 20261012200000")
    utc = compute_ziwei(sky, "/xt 39.9075,116.39723 20261012120000 tz=UTC")
    assert local["epoch_utc"] == utc["epoch_utc"]
    assert [o["single_xy"] for o in local["single_chart"]["objects"]] == [
        o["single_xy"] for o in utc["single_chart"]["objects"]
    ]
    assert (
        local["palace_layer"]["assignment"]["life_branch"]
        != utc["palace_layer"]["assignment"]["life_branch"]
    )


def test_photometric_models_obey_magnitude_distance_and_phase_relationships():
    assert sun_magnitude(1) == pytest.approx(-26.74)
    assert sun_magnitude(10) - sun_magnitude(1) == pytest.approx(5)
    assert moon_magnitude(0, 384400) == pytest.approx(-12.73)
    assert moon_magnitude(90, 384400) == pytest.approx(-10.12756)
    assert moon_magnitude(90, 768800) - moon_magnitude(90, 384400) == pytest.approx(
        5 * math.log10(2)
    )


def test_actual_luminaries_have_model_provenance_and_moon_phase(sky):
    data = compute_ziwei(sky, "/xt 北京 20261012200000")
    objects = {o["key"]: o for o in data["single_chart"]["objects"]}
    assert -26.8 < objects["sun"]["magnitude"] < -26.6
    moon = objects["moon"]
    assert 0 <= moon["phase_angle_deg"] <= 180 and 0 <= moon["illuminated_fraction"] <= 1
    assert -13.5 < moon["magnitude"] < 0
    assert "103.1033K" in moon["magnitude_source"] and "无大气" in moon["magnitude_quality"]


def test_malefic_symbol_rules_match_classical_zi_chou_wu_examples():
    zi = {s["name"]: s["branch"] for s in assign_malefics(2026, 0)}
    assert zi == {
        "擎羊": "午",
        "陀罗": "辰",
        "火星": "丑",
        "铃星": "卯",
        "地空": "亥",
        "地劫": "亥",
    }
    chou = {s["name"]: s["branch"] for s in assign_malefics(2026, 1)}
    assert chou["地空"] == "戌" and chou["地劫"] == "子"
    wu = {s["name"]: s["branch"] for s in assign_malefics(2026, 6)}
    assert wu["地空"] == wu["地劫"] == "巳"


def test_all_sixty_years_and_twelve_hours_have_six_nonphysical_symbols():
    for year in range(1984, 2044):
        for hour in range(12):
            symbols = assign_malefics(year, hour)
            assert len(symbols) == len({s["key"] for s in symbols}) == 6
            assert all(s["branch"] in BRANCHES for s in symbols)
            assert all(s["magnitude"] is s["hip"] is s["naif_id"] is None for s in symbols)
            assert all(s["kind"] == "symbolic" for s in symbols)
            positions = {s["name"]: BRANCHES.index(s["branch"]) for s in symbols}
            assert (positions["擎羊"] - positions["陀罗"]) % 12 == 2
            assert (positions["地空"] + positions["地劫"]) % 12 == 10


def test_selected_time_assigns_six_symbols_without_mixing_real_object_catalog(sky):
    data = compute_ziwei(sky, "/xt 北京 20261012200000")
    symbols = data["palace_layer"]["symbolic_malefics"]
    assert {s["name"]: (s["branch"], s["palace"]) for s in symbols} == {
        "擎羊": ("午", "迁移"),
        "陀罗": ("辰", "官禄"),
        "火星": ("亥", "兄弟"),
        "铃星": ("丑", "父母"),
        "地空": ("丑", "父母"),
        "地劫": ("酉", "子女"),
    }
    assert len(data["single_chart"]["objects"]) == 17
    assert all("altitude_deg" not in s and "ra_date_deg" not in s for s in symbols)
