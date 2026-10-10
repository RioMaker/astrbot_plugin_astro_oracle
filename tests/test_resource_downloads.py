import asyncio

import httpx
import pytest

from local_core import resources, sky_resources


def client_with_transport(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(**kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_model_connection_timeout_reports_source_and_preserves_clean_retry(monkeypatch, tmp_path):
    requests = []

    async def handler(request):
        requests.append(request.url)
        raise httpx.ConnectTimeout("sensitive proxy detail", request=request)

    client_with_transport(monkeypatch, handler)
    for _ in range(2):
        with pytest.raises(
            resources.ResourceDownloadError, match="JPL DE440s.*连接下载站点超时"
        ) as error:
            asyncio.run(resources.prepare(tmp_path))
        assert isinstance(error.value.__cause__, httpx.ConnectTimeout)
        assert "sensitive proxy" not in str(error.value)
        assert not (tmp_path / "ephemeris.json").exists()
        assert not (tmp_path / "de440s.partial.bsp").exists()
    assert len(requests) == 2 and all(str(url) == resources.MODEL_URL for url in requests)


def test_sky_retry_reports_failed_resource_and_removes_partial_file(monkeypatch, tmp_path):
    requests = []

    async def handler(request):
        requests.append(request.url)
        return httpx.Response(503, request=request)

    client_with_transport(monkeypatch, handler)
    with pytest.raises(resources.ResourceDownloadError, match="Hipparcos.*HTTP 503"):
        asyncio.run(sky_resources.prepare_sky(tmp_path))
    assert len(requests) == 3
    assert not (tmp_path / "sky" / "hip_main.dat.part").exists()
    assert not (tmp_path / "sky" / "hip_main.dat").exists()
