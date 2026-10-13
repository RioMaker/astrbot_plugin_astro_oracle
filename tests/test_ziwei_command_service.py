"""紫微入口的请求保真与共用工作线程；模拟返回值仅用于服务路由验证。"""

import asyncio
import io
import sys
import threading
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import httpx
import pytest
from PIL import Image

from local_core.bot_commands import ChartSettings, parse_request
from local_core.bot_service import ChartService
from local_core.bundled_resources import BUNDLE_DIR, resource_files
from local_core.engine import PlanetEngine
from local_core.resources import sha256_file
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei, parse_preview_request

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def test_parsed_request_keeps_timezone_and_old_preview_prefixes():
    request = parse_request("北京 20261012200000 tz=UTC+08:00")
    assert parse_preview_request(request) is request
    for prefix in ("/紫微星图", "/紫薇星图", "/星图", "/xingtu", "/xt", "/star"):
        assert parse_preview_request(f"{prefix} 北京 20261012200000 tz=UTC+08:00") == request
    with pytest.raises(ValueError, match="不处理帮助指令"):
        parse_preview_request(parse_request("help"))


def test_real_compute_accepts_parsed_request_without_rebuilding_time_or_zone():
    core = PlanetEngine(BUNDLE_DIR)
    try:
        sky = SkyChartEngine(core)
        content = "北京 20261012120000 tz=UTC"
        request = parse_request(content)
        typed = compute_ziwei(sky, request, ChartSettings(), NOW)
        original = compute_ziwei(sky, content, ChartSettings(), NOW)
        assert typed == original
        assert typed["timezone"] == "UTC"
        assert typed["epoch_utc"].startswith("2026-10-12T12:00:00")
    finally:
        core.close()


def test_ziwei_delegates_exact_request_on_shared_worker_without_saving_query(monkeypatch, tmp_path):
    service = ChartService(tmp_path)
    owner_thread = threading.get_ident()
    closed, calls = [], []
    sky = SimpleNamespace(core=SimpleNamespace(close=lambda: closed.append(True)))
    service._sky = sky
    request = parse_request("北京 20261012200000 tz=UTC+08:00")
    settings = ChartSettings()
    renderer = ModuleType("local_core.ziwei_linear")

    def generate_ziwei_png(engine, parsed, configured, now):
        assert threading.get_ident() != owner_thread
        calls.append((engine, parsed, configured, now))
        return b"ziwei-service-routing-only"

    renderer.generate_ziwei_png = generate_ziwei_png
    monkeypatch.setitem(sys.modules, renderer.__name__, renderer)

    async def exercise():
        assert await service.generate_ziwei(request, settings, NOW) == b"ziwei-service-routing-only"
        await service.close()
        await service.close()
        with pytest.raises(RuntimeError, match="停止"):
            await service.generate_ziwei(request, settings, NOW)

    asyncio.run(exercise())
    assert calls == [(sky, request, settings, NOW)] and closed == [True]
    assert list(tmp_path.rglob("*")) == []


def test_ziwei_and_old_requests_are_serial_and_cancellation_defers_kernel_close(tmp_path):
    service = ChartService(tmp_path)
    entered, resume = threading.Event(), threading.Event()
    order, worker_threads = [], []
    service._sky = SimpleNamespace(core=SimpleNamespace(close=lambda: order.append("closed")))

    def blocked_ziwei(*args):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert resume.wait(5)
        order.append("ziwei")
        return b"ziwei-service-routing-only"

    def old_chart(*args):
        worker_threads.append(threading.get_ident())
        order.append("old")
        return b"old-service-routing-only"

    service._generate_ziwei = blocked_ziwei
    service._generate = old_chart

    async def exercise():
        first = asyncio.create_task(service.generate_ziwei(parse_request(""), ChartSettings(), NOW))
        assert await asyncio.to_thread(entered.wait, 5)
        second = asyncio.create_task(service.generate(parse_request(""), ChartSettings(), NOW))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        closing = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        assert not order
        resume.set()
        assert await second == b"old-service-routing-only"
        await closing

    asyncio.run(exercise())
    assert order == ["ziwei", "old", "closed"]
    assert len(set(worker_threads)) == 1


def test_real_ziwei_service_is_offline_reuses_cache_and_does_not_save_queries(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "plugin_data" / "astrbot_plugin_astro_oracle"
    data_dir.mkdir(parents=True)
    unrelated = data_dir / "user-config.txt"
    unrelated.write_text("keep local state", encoding="utf-8")
    requests = []

    async def blocked(self, request, *args, **kwargs):
        requests.append(str(request.url))
        raise AssertionError("真实紫微服务集成只允许使用仓库随附资源。")

    monkeypatch.setattr(httpx.AsyncClient, "send", blocked)
    service = ChartService(data_dir)
    worker_threads_before = {
        t.ident for t in threading.enumerate() if t.name.startswith("astro-sky")
    }
    files = resource_files(BUNDLE_DIR)

    def cache_state():
        return {
            name: ((data_dir / name).stat().st_mtime_ns, sha256_file(data_dir / name))
            for name in files
        }

    async def exercise():
        try:
            png = await service.generate_ziwei(
                parse_request("北京 20261012200000"), ChartSettings(), NOW
            )
            with Image.open(io.BytesIO(png)) as image:
                assert image.format == "PNG" and image.size == (2440, 1810)
                image.verify()
            engine = service._sky
            assert service.ready and engine.core.path.parent == data_dir
            first_cache = cache_state()
            for name in files:
                assert sha256_file(data_dir / name) == sha256_file(BUNDLE_DIR / name)
            second = await service.generate_ziwei(
                parse_request("北京 20261012120000 tz=UTC"), ChartSettings(), NOW
            )
            assert second != png  # 同一 UTC 时刻的民用时区标注不同。
            abbreviated = await service.generate_ziwei(
                parse_request("北京 20261012"), ChartSettings(), NOW
            )
            canonical = await service.generate_ziwei(
                parse_request("北京 20261012080000"), ChartSettings(), NOW
            )
            assert abbreviated != canonical  # 同一时刻，图中保留补齐说明与输入精度。
            old = await service.generate(parse_request("北京 20261012200000"), ChartSettings(), NOW)
            with Image.open(io.BytesIO(old)) as image:
                assert image.format == "PNG"
            assert service._sky is engine and first_cache == cache_state()
        finally:
            await service.close()

    asyncio.run(exercise())
    assert not requests and not service.ready
    assert {p.relative_to(data_dir) for p in data_dir.rglob("*") if p.is_file()} == (
        set(files) | {unrelated.relative_to(data_dir)}
    )
    assert unrelated.read_text(encoding="utf-8") == "keep local state"
    assert {
        t.ident for t in threading.enumerate() if t.name.startswith("astro-sky")
    } == worker_threads_before
