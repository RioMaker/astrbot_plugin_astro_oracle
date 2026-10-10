"""打包经来源校验的公共星图资源；只读取明确列出的历表与星表文件。"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from local_core.resources import DATA_DIR, MODEL_FILENAME, inspect_kernel, sha256_file
from local_core.sky_resources import SOURCES

ROOT = Path(__file__).resolve().parents[1]


def resource_files(data_dir):
    ephemeris = json.loads((data_dir / "ephemeris.json").read_text(encoding="utf-8"))
    model = data_dir / MODEL_FILENAME
    if ephemeris.get("filename") != MODEL_FILENAME or ephemeris.get("model") != "DE440s":
        raise ValueError("历表来源记录与预期型号不符。")
    if sha256_file(model) != ephemeris["sha256"]:
        raise ValueError("历表 SHA-256 校验失败，未打包。")
    if inspect_kernel(model) != ephemeris["coverage_tdb_jd"]:
        raise ValueError("历表覆盖范围与记录不符。")
    files = [Path(MODEL_FILENAME), Path("ephemeris.json"), Path("sky/manifest.json")]
    directory = data_dir / "sky"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("parser_version") != 1:
        raise ValueError("星图资源解析版本不匹配。")
    for key, (filename, url) in SOURCES.items():
        record = manifest["sources"][key]
        if record["filename"] != filename or record["url"] != url:
            raise ValueError("星图来源记录与预期来源不符。")
        if sha256_file(directory / filename) != record["sha256"]:
            raise ValueError(f"{key} SHA-256 校验失败，未打包。")
        files.append(Path("sky") / filename)
    if manifest["input_hashes"] != {k: v["sha256"] for k, v in manifest["sources"].items()}:
        raise ValueError("编译数据的来源校验记录不匹配。")
    for key in ("stars", "cities"):
        record = manifest["derived"][key]
        filename = key + ".json.gz"
        if record["filename"] != filename or sha256_file(directory / filename) != record["sha256"]:
            raise ValueError(f"{key} 编译数据校验失败，未打包。")
        files.append(Path("sky") / filename)
    return files


def package_resources(data_dir, output):
    files = resource_files(data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial.zip")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as z:
            for relative in files:
                z.write(data_dir / relative, relative.as_posix())
            z.writestr(
                "OFFLINE_README.md",
                "# 星图离线公共资源\n\n"
                "将本包解压到 AstrBot 提供的 data/plugin_data/astrbot_plugin_astro_oracle/。\n"
                "该目录应直接包含 de440s.bsp、ephemeris.json 和 sky/，不要再套一层文件夹。\n"
                "重载插件后发送 /星图。程序逐项校验并复用这些文件，无需在线下载。\n\n"
                "来源：NASA/JPL DE440s；ESA Hipparcos 1997 / CDS I/239；\n"
                "Stellarium Modern (Sky & Telescope), CC BY-SA 2.0，\n"
                "作者 Paul Krizak、Jonathan E. Piskor、G. Zotti；\n"
                "GeoNames cities1000，CC BY 4.0。原始 URL、日期与 SHA-256 见两个 manifest。\n"
                "星座许可见 sky/modern_st-description.md，"
                "GeoNames 说明见 sky/geonames-readme.txt。\n"
                "资源许可和来源链接见 THIRD_PARTY_NOTICES.md。\n",
            )
            z.write(ROOT / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")
        with zipfile.ZipFile(temporary) as z:
            if z.testzip() is not None:
                raise ValueError("离线包 CRC 校验失败。")
            for relative in files:
                # 按档案内容再次校验，确保打包的源文件没有变化。
                if hashlib.sha256(z.read(relative.as_posix())).hexdigest() != sha256_file(
                    data_dir / relative
                ):
                    raise ValueError("离线包内容与源文件校验值不符。")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "astro_oracle_resources.zip")
    args = parser.parse_args()
    files = package_resources(args.data_dir, args.output)
    print(f"已校验并打包 {len(files)} 个公共资源文件：{args.output.resolve()}")
    print(f"包大小：{args.output.stat().st_size / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main()
