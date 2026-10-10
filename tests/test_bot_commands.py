from datetime import datetime, timezone

import pytest

from local_core.bot_commands import (
    ChartSettings,
    help_text,
    migrate_default_time,
    parse_coordinates,
    parse_request,
    resolve_place,
    resolve_time,
)
from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine

NOW = datetime(2026, 10, 10, 10, 11, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "content,action,time,place",
    [
        ("", "now", None, None),
        ("帮助", "help", None, None),
        ("HELP", "help", None, None),
        ("time 2026-10-10", "time", "2026-10-10", None),
        ("时间 2026-10-10 09:30", "time", "2026-10-10 09:30", None),
        ("地点 New York City", "place", None, "New York City"),
        ("at 2026-10-10 09:30:04 上海", "at", "2026-10-10 09:30:04", "上海"),
        ("时地 2026-10-10 北京", "at", "2026-10-10", "北京"),
        ("at 2026-10-10T09:30:04 New York City", "at", "2026-10-10T09:30:04", "New York City"),
        ("place #1816670", "place", None, "#1816670"),
    ],
)
def test_command_modes_preserve_multiword_locations(content, action, time, place):
    request = parse_request(content)
    assert (request.action, request.time_text, request.place_text) == (action, time, place)


@pytest.mark.parametrize(
    "content",
    [
        "20250",
        "help 北京",
        "time",
        "place",
        "at 2026-10-10",
        "time 2026-02-30",
        "time 2026-10-10 24",
        "time 2026-10-10 12:60",
        "time 2026-10-10 12:30:60",
        "time 2026-10-10 北京",
        "at 2026-10-10 北京 extra tz=bad",
        "x" * 301,
    ],
)
def test_invalid_commands_rejected_before_loading_resources(content):
    with pytest.raises(ValueError):
        parse_request(content)


@pytest.mark.parametrize(
    "value,expected,note",
    [
        ("2026-10-10", "2026-10-10T13:27:41+00:00", "日"),
        ("2026-10-10 09", "2026-10-10T09:27:41+00:00", "时"),
        ("2026-10-10 09:10", "2026-10-10T09:10:41+00:00", "分"),
        ("2026-10-10 09:10:03", "2026-10-10T09:10:03+00:00", "秒"),
    ],
)
def test_only_missing_fields_use_configured_time(value, expected, note):
    result, explanation = resolve_time(parse_request("time " + value), "UTC", "13:27:41", NOW)
    assert result.isoformat() == expected
    assert f"输入到{note}" in explanation
    assert ("补齐" in explanation) == (note != "秒")


def test_current_commands_ignore_default_clock_and_follow_same_instant():
    for content in ("", "place 北京", "place New York City"):
        result, note = resolve_time(parse_request(content), "America/New_York", "12:00:00", NOW)
        assert result == NOW
        assert "当前时刻" in note


def test_foreign_local_time_and_explicit_offset():
    result, _ = resolve_time(
        parse_request("time 2026-10-10 12:00:00"), "America/New_York", "12:00:00", NOW
    )
    assert result.hour == 16
    request = parse_request("at 2026-11-01 01:30:00 New York City tz=UTC-04:00")
    result, _ = resolve_time(request, "America/New_York", "12:00:00", NOW)
    assert result.isoformat() == "2026-11-01T05:30:00+00:00"


def test_fill_before_dst_validation_accepts_date_at_noon_but_rejects_ambiguous_hour():
    result, _ = resolve_time(parse_request("time 2026-11-01"), "America/New_York", "12:00:00", NOW)
    assert result.hour == 17
    for value in ("2026-11-01 01:30:00", "2026-03-08 02:30:00"):
        with pytest.raises(ValueError):
            resolve_time(parse_request("time " + value), "America/New_York", "12:00:00", NOW)


@pytest.mark.parametrize(
    "config",
    [
        {"default_time": "25:00:00"},
        {"default_time": "1:00:00"},
        {"default_place": ""},
        {"magnitude_limit": 9},
        {"magnitude_limit": float("nan")},
        {"show_constellation_lines": "false"},
    ],
)
def test_bad_config_is_explained(config):
    with pytest.raises(ValueError):
        ChartSettings.from_mapping(config)


@pytest.fixture(scope="module")
def places():
    core = PlanetEngine()
    sky = SkyChartEngine(core)
    yield sky.places
    core.close()


def test_default_beijing_and_chinese_place_are_real_unique_matches(places):
    site, zone, source = resolve_place(places, "北京", "UTC")
    assert source["id"] == 1816670
    assert site["latitude"] == 39.9075 and site["longitude"] == 116.39723
    assert zone == "Asia/Shanghai" and site["label"] == "北京"
    assert resolve_place(places, "上海", "UTC")[2]["id"] == 1796236


def test_ambiguous_place_lists_choices_and_id_resolves(places):
    with pytest.raises(ValueError, match="#5128581"):
        resolve_place(places, "New York", "UTC")
    site, zone, source = resolve_place(places, "#5128581", "UTC")
    assert site["label"] == "New York City" and zone == "America/New_York"
    assert source["country"] == "US"
    assert resolve_place(places, "Paris,FR", "UTC")[2]["id"] == 2988507


def test_explicit_coordinates_and_missing_places(places):
    site, zone, _ = resolve_place(places, "39.9,116.4", "Asia/Shanghai")
    assert site["latitude"] == 39.9 and zone == "Asia/Shanghai"
    for query in ("不存在的测试城市xyz", "#0", "91,0", "0,181"):
        with pytest.raises(ValueError):
            resolve_place(places, query, "UTC")


def test_help_describes_all_prefixes_and_current_defaults():
    value = help_text(ChartSettings(default_time="15:42:07"))
    for name in ("/星图", "/xingtu", "/xt", "/star", "time", "place", "at", "15:42:07"):
        assert name in value


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2000", "2000-01-01T08:00:00+00:00"),
        ("200010", "2000-10-01T08:00:00+00:00"),
        ("20010101", "2001-01-01T08:00:00+00:00"),
        ("2000101001", "2000-10-10T01:00:00+00:00"),
        ("200010100100", "2000-10-10T01:00:00+00:00"),
        ("20001010010023", "2000-10-10T01:00:23+00:00"),
        ("2025-02", "2025-02-01T08:00:00+00:00"),
        ("20250102 09:30", "2025-01-02T09:30:00+00:00"),
    ],
)
def test_compact_fields_and_partial_calendar_defaults(value, expected):
    settings = ChartSettings()
    request = parse_request(value)
    moment, note = resolve_time(request, "UTC", settings.default_time, NOW)
    assert moment.isoformat() == expected
    assert "输入到" in note
    assert settings.default_time == "08:00:00"


@pytest.mark.parametrize(
    "text,time,place",
    [
        ("北京", None, "北京"),
        ("北京 20250102", "20250102", "北京"),
        ("20250102 北京", "20250102", "北京"),
        ("New York City 20250102", "20250102", "New York City"),
        ("2025-01-02 09:30 北京", "2025-01-02 09:30", "北京"),
        ("30.25°N 120.5°E 20250102", "20250102", "30.25°N 120.5°E"),
        ("20250102 30 120.5", "20250102", "30 120.5"),
    ],
)
def test_direct_inputs_detect_time_and_location_in_both_orders(text, time, place):
    request = parse_request(text)
    assert request.time_text == time and request.place_text == place
    assert request.action == ("at" if time else "place")


@pytest.mark.parametrize(
    "text,latitude,longitude",
    [
        ("30.25°N 120.5°E", 30.25, 120.5),
        ("120.5°E 30.25°N", 30.25, 120.5),
        ("30.25 N 120.5 E", 30.25, 120.5),
        ("N 30.25 E 120.5", 30.25, 120.5),
        ("30.25° N 120.5° E", 30.25, 120.5),
        ("３０．２５°Ｎ １２０．５°Ｅ", 30.25, 120.5),
        ("30.25S 120.5W", -30.25, -120.5),
        ("-30.25, -120.5", -30.25, -120.5),
        ("30.25，120.5", 30.25, 120.5),
    ],
)
def test_coordinate_format_signs_and_axes(text, latitude, longitude):
    site = parse_coordinates(text)
    assert site["latitude"] == latitude and site["longitude"] == longitude


@pytest.mark.parametrize(
    "text",
    [
        "200",
        "20250",
        "2025010",
        "202500",
        "20250230",
        "2025010224",
        "202501020160",
        "20250102010060",
        "08:30",
        "北京 2025 2026",
        "30.25°N",
        "30°N 40°N",
        "-30°N 120°E",
        "91°N 120°E",
        "30°N 181°E",
    ],
)
def test_ambiguous_missing_year_or_invalid_fields_are_rejected(text):
    with pytest.raises(ValueError):
        parse_request(text)


def test_default_beijing_direct_forms_and_coordinates_use_real_data(places):
    settings = ChartSettings()
    for text in ("20010101", "北京 20010101", "20010101 北京"):
        request = parse_request(text)
        site, zone, source = resolve_place(
            places, request.place_text or settings.default_place, settings.coordinate_timezone
        )
        assert source["id"] == 1816670 and zone == "Asia/Shanghai"
        instant, _ = resolve_time(request, zone, settings.default_time, NOW)
        assert instant.isoformat() == "2001-01-01T00:00:00+00:00"
    request = parse_request("30.25°N 120.5°E 20250102")
    site, zone, _ = resolve_place(places, request.place_text, settings.coordinate_timezone)
    assert site["latitude"] == 30.25 and site["longitude"] == 120.5
    assert resolve_time(request, zone, settings.default_time, NOW)[0].hour == 0


def test_legacy_default_migrates_once_and_custom_value_survives():
    class Config(dict):
        saves = 0

        def save_config(self):
            self.saves += 1

    old = Config(default_time="12:00:00")
    migrate_default_time(old)
    assert old["default_time"] == "08:00:00" and old.saves == 1
    old["default_time"] = "12:00:00"
    migrate_default_time(old)
    assert old["default_time"] == "12:00:00" and old.saves == 1
    custom = Config(default_time="13:27:41")
    migrate_default_time(custom)
    assert custom["default_time"] == "13:27:41" and custom.saves == 1
