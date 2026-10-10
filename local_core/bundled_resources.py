"""仓库随附的固定公共资源快照；只初始化明确列出的公共缓存文件。"""

import json
import shutil
from pathlib import Path

from .resources import MODEL_FILENAME, inspect_kernel, sha256_file
from .sky_resources import SOURCES

BUNDLE_DIR = Path(__file__).resolve().parents[1] / "assets" / "astronomy"


def resource_files(directory):
    ephemeris = json.loads((directory / "ephemeris.json").read_text(encoding="utf-8"))
    model = directory / MODEL_FILENAME
    if ephemeris.get("filename") != MODEL_FILENAME or ephemeris.get("model") != "DE440s":
        raise ValueError("历表来源记录与预期型号不符。")
    if sha256_file(model) != ephemeris["sha256"]:
        raise ValueError("随附历表 SHA-256 校验失败。")
    if inspect_kernel(model) != ephemeris["coverage_tdb_jd"]:
        raise ValueError("历表覆盖范围与记录不符。")
    files = [Path(MODEL_FILENAME), Path("ephemeris.json"), Path("sky/manifest.json")]
    sky = directory / "sky"
    manifest = json.loads((sky / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("parser_version") != 1:
        raise ValueError("星图资源解析版本不匹配。")
    for key, (filename, url) in SOURCES.items():
        record = manifest["sources"][key]
        if record["filename"] != filename or record["url"] != url:
            raise ValueError("星图来源记录与预期来源不符。")
        if sha256_file(sky / filename) != record["sha256"]:
            raise ValueError(f"{key} SHA-256 校验失败。")
        files.append(Path("sky") / filename)
    if manifest["input_hashes"] != {k: v["sha256"] for k, v in manifest["sources"].items()}:
        raise ValueError("编译数据的来源校验记录不匹配。")
    for key in ("stars", "cities"):
        record = manifest["derived"][key]
        filename = key + ".json.gz"
        if record["filename"] != filename or sha256_file(sky / filename) != record["sha256"]:
            raise ValueError(f"{key} 编译数据校验失败。")
        files.append(Path("sky") / filename)
    return files


def seed_bundled_resources(data_dir, bundle_dir=BUNDLE_DIR):
    """经校验后将仓库快照同步到公共缓存；相同文件直接复用。"""
    if not bundle_dir.is_dir():
        return False
    files = resource_files(bundle_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for relative in files:
        source, target = bundle_dir / relative, data_dir / relative
        expected = sha256_file(source)
        if target.is_file() and sha256_file(target) == expected:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".bundled.tmp")
        try:
            shutil.copyfile(source, temporary)
            if sha256_file(temporary) != expected:
                raise ValueError("随附资源复制后的 SHA-256 校验失败。")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return True
