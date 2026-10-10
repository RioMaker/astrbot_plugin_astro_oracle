"""把任务资源包解压到临时目录，禁止 HTTP 请求后通过实际服务生成星图。"""

import argparse
import asyncio
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from local_core.bot_commands import ChartSettings, parse_request
from local_core.bot_service import ChartService
from local_core.resources import DATA_DIR, MODEL_FILENAME, sha256_file
from local_core.sky_resources import SOURCES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = DATA_DIR / "offline-validation"


async def render(directory):
    service = ChartService(directory)
    try:
        png = await service.generate(
            parse_request("time 2026-10-10 20:30:00"),
            ChartSettings(),
            datetime.now(timezone.utc),
        )
        (OUTPUT / "offline-beijing.png").write_bytes(png)
        assert service.ready
    finally:
        await service.close()


def verify(package):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = {
        MODEL_FILENAME,
        "ephemeris.json",
        "sky/manifest.json",
        "sky/stars.json.gz",
        "sky/cities.json.gz",
    }
    files.update("sky/" + value[0] for value in SOURCES.values())
    allowed = files | {"OFFLINE_README.md", "THIRD_PARTY_NOTICES.md"}
    requests = []

    async def blocked(self, request, *args, **kwargs):
        requests.append(str(request.url))
        raise AssertionError("离线包验证中不允许联网。")

    original = httpx.AsyncClient.send
    with tempfile.TemporaryDirectory(prefix="astro-offline-", dir=OUTPUT) as temporary:
        assert Path(temporary).resolve().is_relative_to(OUTPUT.resolve())
        assert Path(temporary).resolve() != OUTPUT.resolve()
        directory = Path(temporary) / "cache"
        directory.mkdir()
        with zipfile.ZipFile(package) as z:
            if set(z.namelist()) != allowed or z.testzip() is not None:
                raise ValueError("资源包文件清单或 CRC 不符。")
            # 只解压明确允许的普通文件，目录层级由文件白名单限定。
            for name in sorted(files):
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        before = {
            p.relative_to(directory).as_posix(): sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file()
        }
        try:
            httpx.AsyncClient.send = blocked
            asyncio.run(render(directory))
        finally:
            httpx.AsyncClient.send = original
        after = {
            p.relative_to(directory).as_posix(): sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file()
        }
        assert before == after and not requests
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "package": package.name,
        "package_sha256": sha256_file(package),
        "resource_file_count": len(files),
        "http_requests": requests,
        "result": "Actual cached preparation and PNG generation succeeded with HTTP disabled",
        "scope": "Local real-resource offline verification; no remote AstrBot/QQ send",
    }
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PASS: 11 resources extracted; HTTP disabled; real PNG generated; cache unchanged.")
    print(OUTPUT / "offline-beijing.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package", type=Path, default=ROOT / "dist" / "astro_oracle_resources.zip"
    )
    args = parser.parse_args()
    verify(args.package)


if __name__ == "__main__":
    main()
