"""核对真实双半球界面的地点检索、时间切换、连线、导出与移动宽度。"""

import json
import socket
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

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
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}")
                expect(page.locator("#latitude")).to_have_value("31.22222")
                page.locator("#place-query").fill("上海")
                page.locator("#search-places").click()
                expect(page.locator(".place-option").first).to_contain_text("Shanghai")
                page.locator(".place-option").first.click()
                expect(page.locator("#timezone")).to_have_value("Asia/Shanghai")
                page.locator("#input-time").fill("2026-10-09")
                page.locator("#calculate").click()
                expect(page.locator("#sky-status")).to_contain_text("已就绪", timeout=15000)
                expect(page.locator("#sky-plots")).to_be_visible()
                expect(page.locator("#upper-counts")).to_contain_text("3 个行星")
                expect(page.locator("#lower-counts")).to_contain_text("4 个行星")
                page.locator("#sky-panel").screenshot(path=OUTPUT / "desktop-panel.png")
                before = page.locator("#sky-upper").evaluate("canvas=>canvas.toDataURL()")
                page.locator("#show-lines").uncheck()
                after = page.locator("#sky-upper").evaluate("canvas=>canvas.toDataURL()")
                assert before != after
                page.locator("#show-lines").check()
                page.locator("#sample-tabs button").nth(3).click()
                expect(page.locator("#sky-stamp")).to_contain_text("12:00:00+08:00", timeout=15000)
                page.locator("#sample-tabs button").first.click()
                expect(page.locator("#sky-stamp")).to_contain_text("00:00:00+08:00", timeout=15000)
                with page.expect_download() as download:
                    page.locator("#export-sky-png").click()
                download.value.save_as(OUTPUT / "export.png")
                with page.expect_download() as download:
                    page.locator("#export-sky-json").click()
                download.value.save_as(OUTPUT / "export.json")
                exported = json.loads((OUTPUT / "export.json").read_text(encoding="utf-8"))
                assert sum(len(scene["planets"]) for scene in exported["hemispheres"].values()) == 7
                assert exported["site"]["latitude"] == 31.22222
                page.locator("#input-time").fill("2026-10-09 12:34:56")
                page.locator("#calculate").click()
                expect(page.locator("#sky-status")).to_contain_text("已就绪", timeout=15000)
                expect(page.locator("#sample-tabs button")).to_have_count(1)
                expect(page.locator("#sky-stamp")).to_contain_text("12:34:56+08:00")
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.locator("#sky-panel").screenshot(path=OUTPUT / "mobile-panel.png")
                assert not errors, errors
                (OUTPUT / "ui-report.json").write_text(
                    json.dumps(
                        {
                            "location_search": True,
                            "dual_hemisphere": True,
                            "line_toggle": True,
                            "sampling_switch": True,
                            "seconds_input": True,
                            "png_json_export": True,
                            "mobile_layout": True,
                            "page_errors": errors,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print(
                    "PASS: location search, both hemispheres, line toggle, time precision/sampling,"
                )
                print("PNG/JSON export, mobile layout and no JavaScript page errors.")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        core.close()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        print(f"Task-owned UI server closed; port {port} released.")


if __name__ == "__main__":
    main()
