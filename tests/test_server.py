import asyncio
import socket
import threading

import httpx
import pytest

from local_core.engine import PlanetEngine
from local_core.server import create_server


@pytest.fixture(scope="module")
def url():
    engine = PlanetEngine()
    server = create_server(engine, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)
    engine.close()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def request(url, method="GET", **kwargs):
    async def run():
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(run())


def test_health_and_static_page(url):
    assert request(url + "/health").json()["ready"] is True
    page = request(url + "/")
    assert page.status_code == 200
    assert "星轨神谕" in page.text
    assert request(url + "/api/info").json()["model"] == "JPL DE440s"


@pytest.mark.parametrize(
    "time,count",
    [("2026-10-09", 7), ("2026-10-09 12", 7), ("2026-10-09 12:34", 7), ("2026-10-09 12:34:56", 1)],
)
def test_api_preserves_input_precision(url, time, count):
    response = request(url + "/api/state", "POST", json={"time": time})
    assert response.status_code == 200
    assert response.json()["sample_count"] == count


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"time": "2026-10-09", "unknown": 1},
        {"time": "1900-02-29"},
        {"time": "1600-01-01"},
        {"time": "2026-10-09", "samples": True},
    ],
)
def test_api_invalid_inputs_return_explanations(url, payload):
    response = request(url + "/api/state", "POST", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]


def test_local_origin_and_json_requirements(url):
    assert request(url + "/api/state", "POST", content="time=2026-10-09").status_code == 415
    assert (
        request(
            url + "/api/state",
            "POST",
            json={"time": "2026-10-09"},
            headers={"Origin": "http://example.test"},
        ).status_code
        == 403
    )


def test_sky_and_offline_places_api(url):
    places = request(url + "/api/places", params={"q": "上海"}).json()["results"]
    assert places[0]["timezone"] == "Asia/Shanghai"
    response = request(
        url + "/api/sky",
        "POST",
        json={
            "epoch": "2026-10-08T16:00:00+00:00",
            "site": {"latitude": 31.22222, "longitude": 121.45806},
        },
    )
    assert response.status_code == 200
    assert sum(len(half["planets"]) for half in response.json()["hemispheres"].values()) == 7


def test_sky_api_invalid_site_returns_explanation(url):
    response = request(
        url + "/api/sky",
        "POST",
        json={"epoch": "2026-10-08T16:00:00+00:00", "site": {"latitude": 91, "longitude": 0}},
    )
    assert response.status_code == 400 and response.json()["error"]
