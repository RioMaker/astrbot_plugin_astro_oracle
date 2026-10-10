import asyncio
import io
import shutil
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from local_core import bot_service
from local_core.bot_commands import ChartSettings, parse_request
from local_core.image_renderer import visual_style
from local_core.resources import DATA_DIR

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def test_real_service_uses_own_resource_directory_and_returns_one_png_without_saving_query(
    tmp_path,
):
    data_dir = tmp_path / "plugin_data" / "astrbot_plugin_astro_oracle"
    data_dir.mkdir(parents=True)
    for name in ("de440s.bsp", "ephemeris.json"):
        shutil.copyfile(DATA_DIR / name, data_dir / name)
    shutil.copytree(DATA_DIR / "sky", data_dir / "sky")
    before = {
        str(p.relative_to(data_dir)): p.stat().st_mtime_ns
        for p in data_dir.rglob("*")
        if p.is_file()
    }
    service = bot_service.ChartService(data_dir)

    async def exercise():
        try:
            settings = ChartSettings(default_time="20:30:11")
            first = await service.generate(parse_request("time 2026-10-10"), settings, NOW)
            exact = await service.generate(parse_request("time 2026-10-10 20:30:11"), settings, NOW)
            with Image.open(io.BytesIO(first)) as image:
                assert image.format == "PNG" and image.size == (1680, 1145)
            # 补齐值相同，天球圆盘区域一致；顶部输入分辨率说明应不同。
            with Image.open(io.BytesIO(first)) as a, Image.open(io.BytesIO(exact)) as b:
                assert (
                    a.crop((30, 173, 1660, 945)).tobytes() == b.crop((30, 173, 1660, 945)).tobytes()
                )
                assert first != exact
            no_lines = await service.generate(
                parse_request("time 2026-10-10"),
                ChartSettings(default_time="20:30:11", lines=False),
                NOW,
            )
            assert no_lines != first
            assert service.ready and service._sky.core.path.parent == data_dir
        finally:
            await service.close()
        assert not service.ready
        with pytest.raises(RuntimeError, match="停止"):
            await service.generate(parse_request(""), ChartSettings(), NOW)

    asyncio.run(exercise())
    after = {
        str(p.relative_to(data_dir)): p.stat().st_mtime_ns
        for p in data_dir.rglob("*")
        if p.is_file()
    }
    assert before == after
    assert not any(t.name.startswith("astro-sky") and t.is_alive() for t in threading.enumerate())


def test_cancelled_request_finishes_worker_before_kernel_close(tmp_path):
    service = bot_service.ChartService(tmp_path)
    entered, resume = threading.Event(), threading.Event()
    order = []

    def blocked(*args):
        service._sky = SimpleNamespace(core=SimpleNamespace(close=lambda: order.append("closed")))
        entered.set()
        assert resume.wait(5)
        order.append("computed")

    service._generate = blocked

    async def exercise():
        task = asyncio.create_task(service.generate(parse_request(""), ChartSettings(), NOW))
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        closing = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        assert not order
        resume.set()
        await closing
        await service.close()

    asyncio.run(exercise())
    assert order == ["computed", "closed"]


def test_initialization_failure_can_retry_and_close_partial_core(monkeypatch, tmp_path):
    service = bot_service.ChartService(tmp_path)
    calls = []

    async def prepare(directory):
        calls.append(directory)

    core = SimpleNamespace(close=lambda: calls.append("closed"))
    monkeypatch.setattr(bot_service, "prepare_all", prepare)
    monkeypatch.setattr(bot_service, "PlanetEngine", lambda directory: core)
    monkeypatch.setattr(
        bot_service, "SkyChartEngine", lambda c: (_ for _ in ()).throw(ValueError("bad"))
    )

    async def exercise():
        for _ in range(2):
            with pytest.raises(ValueError, match="bad"):
                await service.generate(parse_request(""), ChartSettings(), NOW)
            assert not service.ready
        await service.close()

    asyncio.run(exercise())
    assert calls == [tmp_path, "closed", tmp_path, "closed"]


def test_visual_brightness_mapping_and_unknown_magnitude():
    values = [visual_style(m) for m in (-4, 0, 3, 6, 8)]
    assert all(a[0] > b[0] and a[1] > b[1] for a, b in zip(values, values[1:]))
    assert visual_style(None) == (2, 0.6)
