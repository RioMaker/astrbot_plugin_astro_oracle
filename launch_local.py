"""直接以 Python 启动，自动使用项目 .venv，就绪后打开浏览器。"""

import argparse
import asyncio
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> None:
    parser = argparse.ArgumentParser(description="启动星轨神谕本地联合调试")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not PYTHON.exists():
        raise SystemExit("缺少本项目 .venv，请按 README 的准备步骤安装本地依赖。")
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        os.execv(
            str(PYTHON),
            [str(PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    from local_core.engine import PlanetEngine
    from local_core.resources import prepare_all
    from local_core.server import create_server

    asyncio.run(prepare_all())
    engine = PlanetEngine()
    try:
        server = create_server(engine, args.port)
        url = f"http://127.0.0.1:{server.server_port}"
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url + "/health", timeout=1) as response:
                        health = json.load(response)
                    if health.get("ready") and health.get("pid") == os.getpid():
                        break
                except (urllib.error.URLError, TimeoutError, ValueError):
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("服务在 30 秒内未就绪。")
            print(f"服务已就绪：{url}\n按 Ctrl+C 可结束本次服务。", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            while worker.is_alive():
                worker.join(timeout=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
    finally:
        engine.close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
