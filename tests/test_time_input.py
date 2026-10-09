from datetime import timedelta

import pytest

from local_core.time_input import parse_time_input


@pytest.mark.parametrize(
    "text,precision,duration",
    [
        ("2026-10-09", "day", 86400),
        ("2026-10-09 12", "hour", 3600),
        ("2026-10-09 12:34", "minute", 60),
        ("2026-10-09 12:34:56", "second", 1),
    ],
)
def test_resolution_preserves_missing_fields(text, precision, duration):
    window = parse_time_input(text)
    assert window.precision == precision
    assert (window.end - window.start).total_seconds() == duration
    points = window.samples()
    assert all(window.start <= point < window.end for point in points)
    assert points == sorted(set(points))
    assert len(points) == (1 if precision == "second" else 7)


def test_same_instant_across_timezones():
    local = parse_time_input("2026-10-09 08:00:00", "Asia/Shanghai")
    utc = parse_time_input("2026-10-09T00:00:00", "UTC")
    offset = parse_time_input("2026-10-09 08:00:00", "UTC+08:00")
    assert local.start == utc.start == offset.start


@pytest.mark.parametrize("date,hours", [("2026-03-08", 23), ("2026-11-01", 25)])
def test_dst_day_has_actual_elapsed_duration(date, hours):
    window = parse_time_input(date, "America/New_York")
    assert window.end - window.start == timedelta(hours=hours)
    assert all(
        point.astimezone(window.zone).date().isoformat() == date for point in window.samples()
    )


@pytest.mark.parametrize("text", ["2026-03-08 02:30", "2026-11-01 01:30"])
def test_dst_nonexistent_or_ambiguous_time_is_not_guessed(text):
    with pytest.raises(ValueError, match="时区跳变"):
        parse_time_input(text, "America/New_York")


def test_explicit_offset_resolves_overlap():
    earlier = parse_time_input("2026-11-01 01:30", "UTC-04:00")
    later = parse_time_input("2026-11-01 01:30", "UTC-05:00")
    assert later.start - earlier.start == timedelta(hours=1)


def test_hour_ending_at_spring_transition_is_valid():
    window = parse_time_input("2026-03-08 01", "America/New_York")
    assert window.end - window.start == timedelta(hours=1)
    assert window.end.astimezone(window.zone).hour == 3


@pytest.mark.parametrize(
    "text",
    [
        "1900-02-29",
        "2026-13-01",
        "2026-10-09 24",
        "2026-10-09 12:60",
        "2026-10-09 12:34:60",
        "2026/10/09",
        "",
        "-0001-01-01",
    ],
)
def test_invalid_dates_and_unsupported_formats_fail(text):
    with pytest.raises(ValueError):
        parse_time_input(text)


@pytest.mark.parametrize("zone", ["not/a/timezone", "UTC+14:01", "UTC+25:00", ""])
def test_invalid_timezone_fails(zone):
    with pytest.raises(ValueError):
        parse_time_input("2026-10-09", zone)


def test_leap_day_and_natural_sampling_boundaries():
    window = parse_time_input("2000-02-29")
    assert window.end.astimezone(window.zone).date().isoformat() == "2000-03-01"
    points = window.samples()
    assert points[3].astimezone(window.zone).hour == 12
    assert points[-1] == window.end - timedelta(seconds=1)


@pytest.mark.parametrize("count", [1, 26, True, 2.5, "7"])
def test_sampling_count_boundaries(count):
    with pytest.raises(ValueError):
        parse_time_input("2026-10-09").samples(count)
