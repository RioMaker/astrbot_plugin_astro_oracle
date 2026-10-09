"""启动任务自有服务和全新无头浏览器，验证网页并保存本地预览。"""

import json
import socket
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from local_core.engine import PlanetEngine
from local_core.server import create_server

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "browser-validation"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    engine = PlanetEngine()
    server = create_server(engine, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_port
    url = f"http://127.0.0.1:{port}"
    errors, cases = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.locator("#model-status")).to_contain_text("本地已就绪")
                for value, count, label in [
                    ("2026-10-09", 7, "日"),
                    ("2026-10-09 12", 7, "时"),
                    ("2026-10-09 12:34", 7, "分"),
                    ("2026-10-09 12:34:56", 1, "秒"),
                ]:
                    page.locator("#input-time").fill(value)
                    page.locator("#calculate").click()
                    expect(page.locator("#query-status")).to_contain_text("计算完成")
                    expect(page.locator("#sample-tabs button")).to_have_count(count)
                    expect(page.locator("#planet-rows tr")).to_have_count(8)
                    expect(page.locator("#window-title")).to_contain_text(label + "精度")
                    cases.append({"input": value, "precision": label, "samples": count})
                page.locator("#input-time").fill("2026-10-09")
                page.locator("#calculate").click()
                expect(page.locator("#query-status")).to_contain_text("计算完成")
                page.locator("#sample-tabs button").nth(3).click()
                expect(page.locator("#selected-time")).to_contain_text("12:00:00+08:00")
                page.locator("#planet-select").select_option("earth")
                expect(page.locator("#equatorial dd").first).to_have_text("—")
                page.locator("#planet-select").select_option("mercury")
                expect(page.locator("#trend-rows tr")).to_have_count(7)
                page.screenshot(path=OUTPUT / "desktop.png", full_page=True)
                with page.expect_download() as download:
                    page.locator("#export-json").click()
                download.value.save_as(OUTPUT / "export.json")
                exported = json.loads((OUTPUT / "export.json").read_text(encoding="utf-8"))
                assert exported["sample_count"] == 7
                assert exported["provenance"]["ephemeris"]["sha256"] == engine.manifest["sha256"]
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=OUTPUT / "mobile.png", full_page=True)
                page.locator("#input-time").fill("1600-01-01")
                page.locator("#calculate").click()
                expect(page.locator("#error")).to_contain_text("历表覆盖")
                expect(page.locator("#results")).to_be_hidden()
                assert not errors, errors
                report = {
                    "precision_cases": cases,
                    "sample_switch": True,
                    "earth_null": True,
                    "json_export": True,
                    "mobile_no_page_overflow": True,
                    "range_error": True,
                    "page_errors": errors,
                    "ephemeris_sha256": engine.manifest["sha256"],
                }
                (OUTPUT / "report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print("PASS: four precision modes, 8 planets, sample switching, Earth null,")
                print("mobile layout, range errors and no JavaScript page errors.")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        engine.close()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        print(f"Task-owned server closed; port {port} released.")


if __name__ == "__main__":
    main()
