"""同次真实计算的结果快照、bytes 兼容与串行服务生命周期。"""

import asyncio
import io
import json
import threading
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from local_core import ziwei_atlas, ziwei_linear
from local_core.bot_commands import ChartSettings, parse_request
from local_core.bot_service import ChartService
from local_core.bundled_resources import BUNDLE_DIR
from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_correspondence import build_correspondence
from local_core.ziwei_result import ZiweiChartResult

NOW = datetime(2026, 10, 12, 12, 34, 56, 789000, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def sky():
    core = PlanetEngine(BUNDLE_DIR)
    try:
        yield SkyChartEngine(core)
    finally:
        core.close()


def assert_metadata_matches_compute(metadata, data, comparison):
    for key in ("epoch_utc", "epoch_local", "timezone", "time_note", "site", "site_source"):
        assert metadata[key] == data[key]
    assert metadata["chart_profile"] == ziwei_atlas.PROFILE
    for key, value in metadata["traditional"].items():
        assert value == comparison["traditional"][key]
    assert "positions" not in metadata["traditional"]
    assert not {"rows", "hemispheres", "single_chart", "png", "provenance"} & metadata.keys()
    assert len(json.dumps(metadata, ensure_ascii=False, allow_nan=False).encode("utf-8")) < 4096


def test_real_result_uses_one_compute_and_render_and_keeps_legacy_png_identical(sky, monkeypatch):
    captured, counts = {}, {"compute": 0, "compare": 0, "render": 0}
    original_compute = ziwei_linear.compute_ziwei
    original_compare = ziwei_linear.build_correspondence
    original_render = ziwei_atlas.render_ziwei_atlas

    def compute(*args):
        counts["compute"] += 1
        captured["data"] = original_compute(*args)
        return captured["data"]

    def compare(data):
        counts["compare"] += 1
        captured["comparison"] = original_compare(data)
        return captured["comparison"]

    def render(*args):
        counts["render"] += 1
        captured["rendered"] = original_render(*args)
        return captured["rendered"]

    monkeypatch.setattr(ziwei_linear, "compute_ziwei", compute)
    monkeypatch.setattr(ziwei_linear, "build_correspondence", compare)
    monkeypatch.setattr(ziwei_atlas, "render_ziwei_atlas", render)
    request, settings = parse_request("北京 20261012200000"), ChartSettings()
    result = ziwei_linear.generate_ziwei_result(sky, request, settings, NOW)
    assert isinstance(result, ZiweiChartResult)
    assert counts == {"compute": 1, "compare": 1, "render": 1}
    assert result.png == captured["rendered"][0]
    assert_metadata_matches_compute(result.metadata, captured["data"], captured["comparison"])
    assert result.metadata["epoch_utc"] == "2026-10-12T12:00:00+00:00"
    assert result.metadata["traditional"]["lunar"] == {
        "year": 2026,
        "month": 9,
        "day": 3,
        "leap": False,
    }
    assert result.metadata["traditional"]["life_branch"] == "子"
    assert result.metadata["traditional"]["body_branch"] == "申"
    assert result.metadata["traditional"]["bureau"]["number"] == 5
    with pytest.raises(FrozenInstanceError):
        result.png = b"changed"
    original_label = result.metadata["site"]["label"]
    captured["data"]["site"]["label"] = "changed after snapshot"
    captured["comparison"]["traditional"]["lunar"]["day"] = 999
    assert result.metadata["site"]["label"] == original_label
    assert result.metadata["traditional"]["lunar"]["day"] == 3
    assert ziwei_linear.generate_ziwei_png(sky, request, settings, NOW) == result.png
    assert counts == {"compute": 2, "compare": 2, "render": 2}


def test_real_service_result_metadata_matches_compute_and_old_bytes_api():
    service = ChartService(BUNDLE_DIR)
    request, settings = parse_request("北京 20261012200000"), ChartSettings()

    async def exercise():
        try:
            result = await service.generate_ziwei_result(request, settings, NOW)
            data = compute_ziwei(service._sky, request, settings, NOW)
            assert_metadata_matches_compute(result.metadata, data, build_correspondence(data))
            assert service.ready and service._sky.core.path.name == "de440s.bsp"
            assert result.metadata["site_source"]["source"] == "GeoNames cities1000"
            assert result.metadata["site"]["label"] == "北京"
            with Image.open(io.BytesIO(result.png)) as image:
                assert image.format == "PNG" and image.size == (2440, 1810)
            assert await service.generate_ziwei(request, settings, NOW) == result.png
        finally:
            await service.close()
        assert not service.ready
        for method in (service.generate_ziwei_result, service.generate_ziwei):
            with pytest.raises(RuntimeError, match="停止"):
                await method(request, settings, NOW)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "content,settings,epoch,zone,source",
    [
        (
            "",
            ChartSettings(),
            "2026-10-12T12:34:56+00:00",
            "Asia/Shanghai",
            "GeoNames cities1000",
        ),
        (
            "20261012",
            ChartSettings(default_time="06:17:09"),
            "2026-10-11T22:17:09+00:00",
            "Asia/Shanghai",
            "GeoNames cities1000",
        ),
        (
            "30.25,120.5 20261012",
            ChartSettings(default_time="20:30:11", coordinate_timezone="UTC+09:00"),
            "2026-10-12T11:30:11+00:00",
            "UTC+09:00",
            "用户指定经纬度",
        ),
        (
            "30.25,120.5 20261012 tz=UTC",
            ChartSettings(default_time="20:30:11", coordinate_timezone="UTC+09:00"),
            "2026-10-12T20:30:11+00:00",
            "UTC",
            "用户指定经纬度",
        ),
    ],
)
def test_real_service_resolved_defaults_timezones_and_source(
    content, settings, epoch, zone, source
):
    service = ChartService(BUNDLE_DIR)
    request = parse_request(content)

    async def exercise():
        try:
            result = await service.generate_ziwei_result(request, settings, NOW)
            data = compute_ziwei(service._sky, request, settings, NOW)
            assert_metadata_matches_compute(result.metadata, data, build_correspondence(data))
            assert result.metadata["epoch_utc"] == epoch
            assert result.metadata["timezone"] == zone
            assert result.metadata["site_source"]["source"] == source
            if content:
                assert settings.default_time in result.metadata["time_note"]
            else:
                assert "当前时刻" in result.metadata["time_note"]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_cancelled_result_and_legacy_requests_share_worker_and_finish_before_close(tmp_path):
    service = ChartService(tmp_path)
    entered, resume = threading.Event(), threading.Event()
    order, worker_threads = [], []

    def blocked(*args):
        worker_threads.append(threading.get_ident())
        service._sky = SimpleNamespace(core=SimpleNamespace(close=lambda: order.append("closed")))
        if not order:
            entered.set()
            assert resume.wait(5)
        order.append("generated")
        return ZiweiChartResult(b"worker scheduling fixture", {})

    service._generate_ziwei_result = blocked
    service._generate_ziwei = lambda *args: blocked(*args).png

    async def exercise():
        request, settings = parse_request(""), ChartSettings()
        first = asyncio.create_task(service.generate_ziwei_result(request, settings, NOW))
        assert await asyncio.to_thread(entered.wait, 5)
        second = asyncio.create_task(service.generate_ziwei(request, settings, NOW))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        closing = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        assert not order
        resume.set()
        assert await second == b"worker scheduling fixture"
        await closing
        await service.close()

    asyncio.run(exercise())
    assert order == ["generated", "generated", "closed"]
    assert len(worker_threads) == 2 and len(set(worker_threads)) == 1
