"""仅绑定本机的紫微几何实验接口；实时查询不保存，不下载资源。"""

import argparse
import json
import math
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from local_core.bundled_resources import BUNDLE_DIR
from local_core.engine import PlanetEngine
from local_core.resources import sha256_file
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_correspondence import build_correspondence
from tools.infer_ziwei_geometry import SITES, selected_state

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = Path(__file__).with_name("ziwei_geometry_lab.html")
PROFILE = "ziwei-geometry-lab-v1"
HOST, DEFAULT_PORT = "127.0.0.1", 8769
PARAMETERS = {"epoch", "lat", "lon", "tz"}
FONT_FILES = {
    "/fonts/Inter.ttf": (ROOT / "assets/fonts/AstroInter.ttf", "font/ttf"),
    "/fonts/AstroSans.otf": (ROOT / "assets/fonts/AstroSans.otf", "font/otf"),
}


def unit_vector(first_deg, second_deg):
    """两球面角转单位分量；轴序及左右手约定由调用方的坐标框架决定。"""
    first, second = math.radians(first_deg), math.radians(second_deg)
    return [
        math.cos(second) * math.cos(first),
        math.cos(second) * math.sin(first),
        math.sin(second),
    ]


def _normalize(vector):
    if len(vector) != 3:
        raise ValueError("球面向量必须有三个分量。")
    values = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("球面向量分量须为有限数。")
    norm = math.hypot(*values)
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("球面向量的长度须为非零有限数。")
    return [value / norm for value in values]


def spherical_distance_deg(first, second):
    a, b = _normalize(first), _normalize(second)
    cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    return math.degrees(math.atan2(math.hypot(*cross), sum(x * y for x, y in zip(a, b))))


def nearest_seed(vector, seeds, tolerance_deg=1e-9):
    """球面最近种子；同点异标签或等距异标签返回歧义，不强行择一。"""
    if not seeds or not math.isfinite(tolerance_deg) or tolerance_deg < 0:
        raise ValueError("需要种子与非负有限容差。")
    distances = [spherical_distance_deg(vector, seed["vector"]) for seed in seeds]
    minimum = min(distances)
    indices = [i for i, value in enumerate(distances) if abs(value - minimum) <= tolerance_deg]
    branches = sorted({str(seeds[i]["branch"]) for i in indices})
    ambiguous = len(branches) != 1
    return {
        "branch": None if ambiguous else branches[0],
        "ambiguous": ambiguous,
        "candidate_branches": branches,
        "distance_deg": minimum,
        "nearest_seed_indices": indices,
    }


def parse_parameters(parameters, now=None):
    if set(parameters) - PARAMETERS:
        raise ValueError("只接受 epoch、lat、lon、tz 四个参数。")
    zone_name = parameters.get("tz", "Asia/Shanghai")
    if not isinstance(zone_name, str) or not 1 <= len(zone_name) <= 80:
        raise ValueError("tz 须为 IANA 时区名称。")
    try:
        zone = ZoneInfo(zone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("tz 须为有效 IANA 时区，例如 Asia/Shanghai。") from exc
    epoch = parameters.get("epoch", "now")
    if not isinstance(epoch, str) or not 1 <= len(epoch) <= 80:
        raise ValueError("epoch 须为 now 或含明确 UTC 偏移的 ISO 时间。")
    if epoch.casefold() == "now":
        moment = now if now is not None else datetime.now(timezone.utc)
    else:
        try:
            moment = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("epoch 须为含明确 UTC 偏移的 ISO 时间。") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("epoch 必须包含明确偏移，如 +08:00 或 Z；不能使用无时区时间。")
    moment = moment.astimezone(timezone.utc)
    local = moment.astimezone(zone)
    if not 1900 <= moment.year <= 2100 or not 1900 <= local.year <= 2100:
        raise ValueError("UTC 与当地民用年份须在 1900–2100 年。")
    try:
        latitude = float(parameters.get("lat", SITES[0]["latitude"]))
        longitude = float(parameters.get("lon", SITES[0]["longitude"]))
    except (ValueError, TypeError) as exc:
        raise ValueError("lat 与 lon 须为有限数。") from exc
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("lat 与 lon 须为有限数。")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("lat 范围为 −90 至 90，lon 范围为 −180 至 180。")
    site = {
        "id": "interactive",
        "latitude": latitude,
        "longitude": longitude,
        "elevation_m": 0.0,
        "timezone": zone_name,
        "label": "北京"
        if (latitude, longitude) == (SITES[0]["latitude"], SITES[0]["longitude"])
        else "自定义观测点",
    }
    return moment, site


class GeometryLab:
    def __init__(self, data_dir=BUNDLE_DIR):
        self._closed = False
        self.core = PlanetEngine(data_dir)
        try:
            self.sky = SkyChartEngine(self.core)
            star_file = data_dir / "sky" / self.sky.manifest["derived"]["stars"]["filename"]
            self.provenance = {
                "code_version": PROFILE,
                "core": self.core.provenance,
                "ephemeris": {
                    "model": self.core.manifest["model"],
                    "sha256": sha256_file(self.core.path),
                    "coverage": self.core.coverage,
                },
                "star_catalog": {
                    "filename": star_file.name,
                    "sha256": sha256_file(star_file),
                    "source": self.sky.manifest["sources"]["hipparcos"],
                },
                "sky_chart_algorithm_sha256": self.sky.code_hash,
                "code_sha256": {
                    name: sha256_file(ROOT / name)
                    for name in (
                        "tools/ziwei_geometry_lab.py",
                        "tools/ziwei_geometry_lab.html",
                        "tools/infer_ziwei_geometry.py",
                        "local_core/ziwei_correspondence.py",
                        "local_core/ziwei_traditional.py",
                        "local_core/ziwei_palaces.py",
                    )
                },
                "libraries": {
                    name: version(name)
                    for name in ("skyfield", "jplephem", "numpy", "lunar-python", "tzdata")
                },
            }
        except BaseException:
            self.core.close()
            raise

    def state(self, parameters, now=None):
        if self._closed:
            raise RuntimeError("实验服务已关闭。")
        moment, site = parse_parameters(parameters, now)
        state = selected_state(self.sky, moment.isoformat(), site)
        comparison = build_correspondence(state)
        rows = []
        for row in comparison["rows"]:
            alt, az = math.radians(row["altitude_deg"]), math.radians(row["azimuth_deg"])
            rows.append(
                {
                    **row,
                    "unit_vector": unit_vector(row["ra_date_deg"], row["dec_date_deg"]),
                    "vector_horizontal": [
                        math.cos(alt) * math.cos(az),
                        math.cos(alt) * math.sin(az),
                        math.sin(alt),
                    ],
                }
            )
        t = self.core.ts.from_datetime(moment)
        latitude = math.radians(site["latitude"])
        theta = math.radians(float(t.gast) * 15 + site["longitude"])
        transform = [
            [
                -math.sin(latitude) * math.cos(theta),
                -math.sin(latitude) * math.sin(theta),
                math.cos(latitude),
            ],
            [-math.sin(theta), math.cos(theta), 0.0],
            [
                math.cos(latitude) * math.cos(theta),
                math.cos(latitude) * math.sin(theta),
                math.sin(latitude),
            ],
        ]
        return {
            "epoch_utc": state["epoch_utc"],
            "epoch_local": state["epoch_local"],
            "site": site,
            "traditional": comparison["traditional"],
            "rows": rows,
            "provenance": self.provenance,
            "frames": {
                "origin": "WGS84 站心",
                "unit_vector": "日期真赤道；x=春分点，y=赤经90°，z=北天极",
                "vector_horizontal": "x=北，y=东，z=天顶；无大气折射",
                "equatorial_to_horizontal": transform,
                "association": "同名/编号的选定天体展示；不把传统地支当真实空间宫界",
            },
        }

    def close(self):
        if not self._closed:
            self._closed = True
            self.core.close()


class GeometryHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 不将带时间/地点的请求 URL 写入标准错误或访问日志。
        pass

    def _response(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/api/state":
            try:
                parameters = parse_qs(url.query, keep_blank_values=True, max_num_fields=8)
                if any(len(values) != 1 for values in parameters.values()):
                    raise ValueError("每个参数只能提供一次。")
                result = self.server.lab.state(
                    {name: values[0] for name, values in parameters.items()}
                )
            except ValueError as exc:
                self._response(400, {"error": str(exc)})
                return
            except Exception:
                self._response(500, {"error": "本地真实计算失败，请检查资源与服务状态。"})
                return
            self._response(200, result)
            return
        if url.path == "/":
            try:
                body = PAGE_PATH.read_bytes()
            except FileNotFoundError:
                self._response(503, {"error": "本地实验页面尚未生成。"})
                return
            self._response(200, body, "text/html; charset=utf-8")
            return
        if url.path in FONT_FILES:
            path, content_type = FONT_FILES[url.path]
            try:
                body = path.read_bytes()
            except FileNotFoundError:
                self._response(503, {"error": "本地字体资源缺失。"})
                return
            self._response(200, body, content_type)
            return
        self._response(404, {"error": "未找到本地实验资源。"})


class GeometryServer(HTTPServer):
    def __init__(self, port=DEFAULT_PORT, lab=None):
        self.lab = lab if lab is not None else GeometryLab()
        try:
            super().__init__((HOST, port), GeometryHandler)
        except BaseException:
            self.lab.close()
            raise

    def server_close(self):
        try:
            super().server_close()
        finally:
            self.lab.close()


def create_server(port=DEFAULT_PORT):
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("端口须为 0–65535 的整数；0 由操作系统选择空闲端口。")
    return GeometryServer(port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="绑定本地端口后打开浏览器")
    args = parser.parse_args()
    server = create_server(args.port)
    url = f"http://{HOST}:{server.server_address[1]}"
    print(f"本地实验：{url}", flush=True)
    try:
        if args.open:
            webbrowser.open(url)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
