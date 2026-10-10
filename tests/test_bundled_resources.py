import asyncio
import io
from datetime import datetime, timezone

import httpx
import pytest
from PIL import Image

from local_core.bot_commands import ChartSettings, parse_request
from local_core.bot_service import ChartService
from local_core.bundled_resources import BUNDLE_DIR, resource_files, seed_bundled_resources
from local_core.resources import sha256_file


def test_fresh_framework_cache_generates_real_chart_from_repo_with_http_disabled(
    monkeypatch, tmp_path
):
    data_dir = tmp_path / "plugin_data" / "astrbot_plugin_astro_oracle"
    data_dir.mkdir(parents=True)
    unrelated = data_dir / "user-config.txt"
    unrelated.write_text("keep local state", encoding="utf-8")
    requests = []

    async def blocked(self, request, *args, **kwargs):
        requests.append(str(request.url))
        raise AssertionError("仓库随附资源测试不允许联网。")

    monkeypatch.setattr(httpx.AsyncClient, "send", blocked)
    service = ChartService(data_dir)

    async def exercise():
        try:
            png = await service.generate(
                parse_request("time 2026-10-10 20:30:00"),
                ChartSettings(),
                datetime(2026, 10, 10, tzinfo=timezone.utc),
            )
            with Image.open(io.BytesIO(png)) as image:
                assert image.size == (1680, 1145) and image.format == "PNG"
            assert service.ready and service._sky.core.path.parent == data_dir
        finally:
            await service.close()

    asyncio.run(exercise())
    assert not requests
    files = resource_files(BUNDLE_DIR)
    assert len(files) == 11
    for name in files:
        assert sha256_file(data_dir / name) == sha256_file(BUNDLE_DIR / name)
    before = {name: (data_dir / name).stat().st_mtime_ns for name in files}
    assert seed_bundled_resources(data_dir)
    assert before == {name: (data_dir / name).stat().st_mtime_ns for name in files}
    assert unrelated.read_text(encoding="utf-8") == "keep local state"


def test_incomplete_bundled_snapshot_is_rejected_before_target_mutation(tmp_path):
    broken = tmp_path / "bundle"
    broken.mkdir()
    (broken / "ephemeris.json").write_bytes((BUNDLE_DIR / "ephemeris.json").read_bytes())
    destination = tmp_path / "cache"
    with pytest.raises(FileNotFoundError):
        seed_bundled_resources(destination, broken)
    assert not destination.exists()
