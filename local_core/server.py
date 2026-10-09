"""仅绑定本机的调试 API 与静态网页。"""

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import PlanetEngine
from .resources import DATA_DIR

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
}


def create_server(engine: PlanetEngine, port: int = 8768) -> ThreadingHTTPServer:
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, content: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, value: dict, status: int = 200) -> None:
            content = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_bytes(content, "application/json", status)

        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_json({"app": "astro_oracle", "ready": True, "pid": os.getpid()})
            elif self.path == "/api/info":
                self.send_json(engine.info())
            elif self.path in STATIC_FILES:
                filename, content_type = STATIC_FILES[self.path]
                self.send_bytes((WEB_DIR / filename).read_bytes(), content_type)
            else:
                self.send_json({"error": "页面不存在。"}, 404)

        def do_POST(self) -> None:
            if self.path != "/api/state":
                self.send_json({"error": "接口不存在。"}, 404)
                return
            if self.headers.get_content_type() != "application/json":
                self.send_json({"error": "请使用 JSON 请求。"}, 415)
                return
            origin = self.headers.get("Origin")
            if origin and origin not in {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }:
                self.send_json({"error": "仅允许本地页面调用。"}, 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 4096:
                    raise ValueError("请求大小不正确。")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("请求必须是 JSON 对象。")
                if set(request) - {"time", "timezone", "samples"}:
                    raise ValueError("请求包含不支持的字段。")
                with lock:
                    result = engine.compute(
                        request.get("time", ""),
                        request.get("timezone", "Asia/Shanghai"),
                        request.get("samples", 7),
                    )
                self.send_json(result)
            except (ValueError, UnicodeError) as exc:
                self.send_json({"error": str(exc)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send_json({"error": "计算发生内部错误，请查看本地服务日志。"}, 500)
                raise

        def log_message(self, format: str, *args) -> None:
            # 不记录请求正文中的日期、地点或其他资料。
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="星轨神谕本地行星状态服务")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    engine = PlanetEngine(args.data_dir)
    try:
        server = create_server(engine, args.port)
        print(f"星轨神谕已就绪：http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
