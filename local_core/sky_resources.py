"""准备真实星表、星座连线与离线城市检索数据。"""

import asyncio
import gzip
import io
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .resources import DATA_DIR, ResourceDownloadError, sha256_file

SOURCES = {
    "hipparcos": ("hip_main.dat", "https://cdsarc.cds.unistra.fr/ftp/cats/I/239/hip_main.dat"),
    "hipparcos_readme": (
        "hipparcos-readme.txt",
        "https://cdsarc.cds.unistra.fr/ftp/cats/I/239/ReadMe",
    ),
    "constellations": (
        "modern_st.json",
        "https://raw.githubusercontent.com/Stellarium/stellarium/master/skycultures/modern_st/index.json",
    ),
    "culture_license": (
        "modern_st-description.md",
        "https://raw.githubusercontent.com/Stellarium/stellarium/master/skycultures/modern_st/description.md",
    ),
    "cities": ("cities1000.zip", "https://download.geonames.org/export/dump/cities1000.zip"),
    "cities_readme": (
        "geonames-readme.txt",
        "https://download.geonames.org/export/dump/readme.txt",
    ),
}
SOURCE_LABELS = {
    "hipparcos": "Hipparcos 恒星目录",
    "hipparcos_readme": "Hipparcos 目录说明",
    "constellations": "Stellarium 星座图形",
    "culture_license": "Stellarium 星座许可说明",
    "cities": "GeoNames 地点库",
    "cities_readme": "GeoNames 地点库说明",
}


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


async def download(client, path, url):
    partial = path.with_suffix(path.suffix + ".part")
    try:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            count = 0
            with partial.open("wb") as stream:
                async for chunk in response.aiter_bytes(262144):
                    count += len(chunk)
                    if count > 128 * 1024 * 1024:
                        raise ValueError("星图资源大小超出预期，停止下载。")
                    stream.write(chunk)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def compile_stars(path, culture):
    endpoints = {
        hip for item in culture["constellations"] for line in item["lines"] for hip in line
    }
    names = {
        int(key.split()[1]): value[0].get("native", value[0].get("english", ""))
        for key, value in culture.get("common_names", {}).items()
        if key.startswith("HIP ") and value
    }
    stars, total, invalid = [], 0, 0
    with path.open(encoding="ascii") as stream:
        for line in stream:
            fields = line.rstrip().split("|")
            if len(fields) < 14:
                raise ValueError("Hipparcos 字段不完整。")
            total += 1
            try:
                hip = int(fields[1])
                mag, ra, dec, pmra, pmdec = [float(fields[i]) for i in (5, 8, 9, 12, 13)]
                if not all(math.isfinite(x) for x in (mag, ra, dec, pmra, pmdec)):
                    raise ValueError("缺少位置/自行/星等")
                parallax = max(0.0, float(fields[11])) if fields[11].strip() else 0.0
            except ValueError:
                invalid += 1
                continue
            if mag <= 8 or hip in endpoints:
                stars.append([hip, mag, ra / 15, dec, parallax, pmra, pmdec, names.get(hip, "")])
    if total < 100000 or len(stars) < 1000:
        raise ValueError("Hipparcos 数据规模异常。")
    return {
        "epoch_year": 1991.25,
        "rows": stars,
        "original_count": total,
        "invalid_count": invalid,
        "columns": [
            "hip",
            "vmag",
            "ra_hours",
            "dec_degrees",
            "parallax_mas",
            "pmra",
            "pmdec",
            "name",
        ],
    }


def compile_cities(path):
    rows = []
    with zipfile.ZipFile(path) as archive:
        member = archive.getinfo("cities1000.txt")
        if member.file_size > 300 * 1024 * 1024:
            raise ValueError("城市数据展开大小异常。")
        with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8") as stream:
            for line in stream:
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 19:
                    raise ValueError("GeoNames 字段不完整。")
                rows.append(
                    [
                        int(fields[0]),
                        fields[1],
                        fields[2],
                        fields[3],
                        float(fields[4]),
                        float(fields[5]),
                        fields[8],
                        fields[17],
                        int(fields[14] or 0),
                    ]
                )
    if len(rows) < 10000:
        raise ValueError("城市数据规模异常。")
    return {
        "rows": rows,
        "columns": [
            "id",
            "name",
            "ascii",
            "aliases",
            "lat",
            "lon",
            "country",
            "timezone",
            "population",
        ],
    }


async def prepare_sky(data_dir=DATA_DIR):
    directory = data_dir / "sky"
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    records = manifest.setdefault("sources", {})
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=httpx.Timeout(120, connect=20)
    ) as client:
        for key, (filename, url) in SOURCES.items():
            path = directory / filename
            record = records.get(key)
            if path.exists() and record and record["sha256"] == sha256_file(path):
                continue
            print(f"准备星图资源：{key}", flush=True)
            for attempt in range(3):
                try:
                    await download(client, path, url)
                    break
                except (httpx.HTTPError, OSError) as exc:
                    if attempt == 2:
                        if isinstance(exc, httpx.HTTPError):
                            raise ResourceDownloadError(SOURCE_LABELS[key], exc) from exc
                        raise
                    await asyncio.sleep(1)
            records[key] = {
                "url": url,
                "filename": filename,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "obtained_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            write_json(manifest_path, manifest)
    inputs = {key: value["sha256"] for key, value in records.items()}
    derived = manifest.get("derived", {})
    valid = manifest.get("parser_version") == 1 and manifest.get("input_hashes") == inputs
    for record in derived.values():
        path = directory / record["filename"]
        valid = valid and path.exists() and sha256_file(path) == record["sha256"]
    if valid and set(derived) == {"stars", "cities"}:
        return manifest
    culture = json.loads((directory / SOURCES["constellations"][0]).read_text(encoding="utf-8"))
    license_text = (directory / SOURCES["culture_license"][0]).read_text(encoding="utf-8")
    if len(culture["constellations"]) != 88 or "CC BY-SA 2.0" not in license_text:
        raise ValueError("星座数据结构或许可与预期不符，请重新核对来源。")
    datasets = {
        "stars": compile_stars(directory / SOURCES["hipparcos"][0], culture),
        "cities": compile_cities(directory / SOURCES["cities"][0]),
    }
    derived = {}
    for key, value in datasets.items():
        path = directory / (key + ".json.gz")
        path.write_bytes(
            gzip.compress(
                json.dumps(
                    value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ).encode("utf-8"),
                mtime=0,
            )
        )
        derived[key] = {
            "filename": path.name,
            "sha256": sha256_file(path),
            "count": len(value["rows"]),
        }
    manifest.update(
        {
            "parser_version": 1,
            "input_hashes": inputs,
            "derived": derived,
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            "credits": {
                "stars": "ESA Hipparcos (1997), CDS I/239",
                "constellations": "Stellarium Modern (Sky & Telescope); CC BY-SA 2.0",
                "cities": "GeoNames cities1000; CC BY 4.0",
            },
        }
    )
    write_json(manifest_path, manifest)
    print(
        f"星图资源就绪：{derived['stars']['count']} 颗恒星，{derived['cities']['count']} 个地名。",
        flush=True,
    )
    return manifest


def load_dataset(directory, manifest, key):
    record = manifest["derived"][key]
    path = directory / record["filename"]
    if sha256_file(path) != record["sha256"]:
        raise ValueError("星图数据校验值不符，请检查资源。")
    return json.loads(gzip.decompress(path.read_bytes()))
