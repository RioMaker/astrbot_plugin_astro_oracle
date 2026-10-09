import json

import numpy as np
import pytest

from local_core.engine import PlanetEngine


@pytest.fixture(scope="module")
def engine():
    core = PlanetEngine()
    yield core
    core.close()


def test_real_ephemeris_returns_finite_unit_consistent_states(engine):
    result = engine.compute("2026-10-09")
    assert len(result["snapshots"]) == 7
    for snapshot in result["snapshots"]:
        assert len(snapshot["planets"]) == 8
        for body in snapshot["planets"]:
            state = body["heliocentric"]
            assert np.isfinite(state["position_au"]).all()
            assert np.isfinite(state["velocity_km_s"]).all()
            assert np.linalg.norm(state["position_au"]) == pytest.approx(state["distance_au"])
            assert np.linalg.norm(state["velocity_km_s"]) == pytest.approx(state["speed_km_s"])
            assert 0.2 < state["distance_au"] < 40
            assert 1 < state["speed_km_s"] < 100
            geo = body["geocentric_apparent"]
            if body["key"] == "earth":
                assert geo is None
            else:
                assert 0 <= geo["ecliptic_longitude_deg"] < 360
                assert -90 <= geo["ecliptic_latitude_deg"] <= 90
                assert 0 <= geo["right_ascension_deg"] < 360
                assert geo["distance_au"] > 0
    json.dumps(result, allow_nan=False)


def test_timezone_equivalence_produces_identical_planet_states(engine):
    local = engine.compute("2026-10-09 08:00:00", "Asia/Shanghai")
    utc = engine.compute("2026-10-09 00:00:00", "UTC")
    assert local["snapshots"][0]["planets"] == utc["snapshots"][0]["planets"]


def test_supplied_second_matches_same_day_sampling(engine):
    day = engine.compute("2026-10-09")
    second = engine.compute("2026-10-09 12:00:00")
    assert second["sample_count"] == 1
    batch = day["snapshots"][3]
    single = second["snapshots"][0]
    assert batch["utc"] == single["utc"]
    assert batch["tdb_jd"] == single["tdb_jd"]
    for first, other in zip(batch["planets"], single["planets"]):
        assert first["heliocentric"] == other["heliocentric"]
        if first["geocentric_apparent"] is None:
            assert other["geocentric_apparent"] is None
            continue
        for key in (
            "ecliptic_longitude_deg",
            "ecliptic_latitude_deg",
            "right_ascension_deg",
            "declination_deg",
            "distance_au",
        ):
            # 向量化角度运算在最后几个浮点位存在舍入差异，实测最大 2.85e-14 度。
            assert first["geocentric_apparent"][key] == pytest.approx(
                other["geocentric_apparent"][key], abs=1e-12, rel=0
            )


@pytest.mark.parametrize("text", ["1600-01-01", "2300-01-01"])
def test_outside_actual_ephemeris_range_is_rejected(engine, text):
    with pytest.raises(ValueError, match="历表覆盖"):
        engine.compute(text)


def test_one_second_motion_agrees_with_recorded_velocity(engine):
    before = engine.compute("2026-10-09 11:59:59")["snapshots"][0]["planets"]
    middle = engine.compute("2026-10-09 12:00:00")["snapshots"][0]["planets"]
    after = engine.compute("2026-10-09 12:00:01")["snapshots"][0]["planets"]
    for first, center, last in zip(before, middle, after):
        difference = (
            (
                np.array(last["heliocentric"]["position_au"])
                - np.array(first["heliocentric"]["position_au"])
            )
            * 149597870.7
            / 2
        )
        np.testing.assert_allclose(
            difference, center["heliocentric"]["velocity_km_s"], rtol=0, atol=1e-5
        )


def test_target_identity_and_provenance_are_explicit(engine):
    info = engine.info()
    assert len(info["provenance"]["ephemeris"]["sha256"]) == 64
    assert info["provenance"]["ephemeris"]["source_url"].startswith("https://naif.jpl.nasa.gov/")
    assert {
        body["name"] for body in info["planets"] if body["target_kind"] == "system_barycenter"
    } == {"火星", "木星", "土星", "天王星", "海王星"}
