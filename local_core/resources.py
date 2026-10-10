"""显式准备 JPL 历表；查询路径只读取本地资源，不隐式联网。"""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from skyfield.api import load_file

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MODEL_FILENAME = "de440s.bsp"
MODEL_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"
REQUIRED_TARGETS = (10, 199, 299, 399, 4, 5, 6, 7, 8)


class ResourceDownloadError(RuntimeError):
    """公共资源下载失败；只对用户展示资源名称和安全的失败类型。"""

    def __init__(self, resource: str, error: httpx.HTTPError):
        if isinstance(error, httpx.ConnectTimeout):
            reason = "连接下载站点超时"
        elif isinstance(error, httpx.ReadTimeout):
            reason = "读取下载内容超时"
        elif isinstance(error, httpx.ConnectError):
            reason = "无法连接下载站点"
        elif isinstance(error, httpx.HTTPStatusError):
            reason = f"下载站点返回 HTTP {error.response.status_code}"
        else:
            reason = "网络请求失败"
        self.resource = resource
        self.reason = reason
        super().__init__(f"{resource}下载失败：{reason}。")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_kernel(path: Path) -> dict:
    kernel = load_file(str(path))
    try:
        for target in REQUIRED_TARGETS:
            kernel[target]
        return {
            "start": max(segment.spk_segment.start_jd for segment in kernel.segments),
            "end": min(segment.spk_segment.end_jd for segment in kernel.segments),
        }
    finally:
        kernel.close()


async def prepare(data_dir: Path = DATA_DIR) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / MODEL_FILENAME
    manifest_path = data_dir / "ephemeris.json"
    if target.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("sha256") != sha256_file(target):
            raise ValueError("本地历表校验值与来源记录不符，请先检查文件，程序未覆盖它。")
        inspect_kernel(target)
        print(f"使用已校验的本地历表：{target}")
        return target
    downloaded = not target.exists()
    if downloaded:
        partial = data_dir / "de440s.partial.bsp"
        print(f"下载 JPL DE440s：{MODEL_URL}", flush=True)
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=httpx.Timeout(120, connect=20)
            ) as client:
                async with client.stream("GET", MODEL_URL) as response:
                    response.raise_for_status()
                    size, reported = 0, 0
                    with partial.open("wb") as output:
                        async for chunk in response.aiter_bytes(262144):
                            size += len(chunk)
                            if size > 100 * 1024 * 1024:
                                raise ValueError("DE440s 下载大小异常，已停止。")
                            output.write(chunk)
                            if size - reported >= 8 * 1024 * 1024:
                                print(f"已下载 {size / 1024 / 1024:.1f} MiB", flush=True)
                                reported = size
            inspect_kernel(partial)
            partial.replace(target)
        except httpx.HTTPError as exc:
            raise ResourceDownloadError("JPL DE440s 历表", exc) from exc
        finally:
            partial.unlink(missing_ok=True)
    manifest = {
        "schema_version": 1,
        "model": "DE440s",
        "filename": target.name,
        "source_url": MODEL_URL if downloaded else None,
        "obtained_at_utc": datetime.now(timezone.utc).isoformat() if downloaded else None,
        "bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "coverage_tdb_jd": inspect_kernel(target),
    }
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
    print(f"历表就绪：{target}；SHA-256 {manifest['sha256']}", flush=True)
    return target


async def prepare_all(data_dir: Path = DATA_DIR) -> None:
    from .sky_resources import prepare_sky

    await prepare(data_dir)
    await prepare_sky(data_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="准备星轨神谕本地计算资源")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    asyncio.run(prepare_all(args.data_dir))


if __name__ == "__main__":
    main()
