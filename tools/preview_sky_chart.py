"""用真实站心 API 独立预览双半球绘图组件，结束后释放测试端口。"""

import asyncio
import json
import socket
import threading
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from local_core.engine import PlanetEngine
from local_core.server import create_server

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "sky-validation"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    core = PlanetEngine()
    server = create_server(core, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port
    url = f"http://127.0.0.1:{port}"
    try:

        async def fetch():
            async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
                response = await client.post(
                    url + "/api/sky",
                    json={
                        "epoch": "2026-10-08T16:00:00+00:00",
                        "site": {
                            "latitude": 31.22222,
                            "longitude": 121.45806,
                            "label": "上海 · GeoNames 调试位置",
                        },
                        "timezone": "Asia/Shanghai",
                        "magnitude_limit": 6,
                    },
                )
                response.raise_for_status()
                return response.json()

        data = asyncio.run(fetch())
        (OUTPUT / "scene.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 780})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url + "/health")
                page.set_content("""<html lang="zh-CN"><meta charset="utf-8"><style>
                body{margin:0;padding:26px;background:#101b25;color:#d4e9e0;
                font:14px "Microsoft YaHei",sans-serif}
                h1{font-size:24px}p{color:#9bb2b6}.plots{display:flex;gap:24px}
                .card{background:#182630;border:1px solid #344c54;padding:14px;border-radius:12px}
                canvas{display:block;width:548px;aspect-ratio:1}h2{font-size:16px;margin:0 0 10px}
                </style><h1>星轨神谕 · 真实数据双半球独立预览</h1>
                <p>上海 WGS84 31.22222°N / 121.45806°E · 2026-10-09 00:00:00 +08:00</p>
                <div class="plots"><div class="card"><h2>上半球 · 天顶中心 / 地平线以上</h2>
                <canvas id="upper"></canvas></div>
                <div class="card"><h2>暗面 · 天底中心 / 地球遮挡</h2>
                <canvas id="lower"></canvas></div></div></html>""")
                page.add_script_tag(url=url + "/sky.js")
                page.evaluate(
                    "data=>{for(const h of ['upper','lower'])"
                    "AstroSky.render(document.getElementById(h),data,h);}",
                    data,
                )
                assert not errors, errors
                assert page.evaluate(
                    "AstroSky.style(-1).radius > AstroSky.style(2).radius && "
                    "AstroSky.style(2).radius > AstroSky.style(6).radius"
                )
                page.screenshot(path=OUTPUT / "component-preview.png", full_page=True)
                print("PASS: real-data component preview, magnitude ordering and no JS errors.")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        core.close()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        print(f"Task-owned preview server closed; port {port} released.")


if __name__ == "__main__":
    main()
