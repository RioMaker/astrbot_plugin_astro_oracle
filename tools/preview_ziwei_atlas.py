"""显式保存指令同款紫微关联图；正常消息请求仅返回内存 PNG。"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from local_core.engine import PlanetEngine
from local_core.resources import DATA_DIR, prepare_all
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_atlas import CJK, INTER, PROFILE, render_ziwei_atlas
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_correspondence import build_correspondence


async def preview(args):
    await prepare_all(DATA_DIR)
    core = PlanetEngine(DATA_DIR)
    try:
        data = compute_ziwei(SkyChartEngine(core), args.input)
        comparison = build_correspondence(data)
        png, layout = render_ziwei_atlas(data, comparison)
        root = Path(__file__).resolve().parents[1]
        sources = [
            "ziwei_atlas.py",
            "ziwei_association.py",
            "ziwei_linear.py",
            "ziwei_names.py",
            "ziwei_linear_theme.py",
            "ziwei_chart.py",
            "ziwei_correspondence.py",
            "ziwei_traditional.py",
        ]
        payload = {
            "profile": PROFILE,
            "request": args.input,
            "data": data,
            "comparison": comparison,
            "layout": layout,
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "code_sha256": {
                name: hashlib.sha256((root / "local_core" / name).read_bytes()).hexdigest()
                for name in sources
            },
            "font_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (INTER, CJK)
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(png)
        args.output.with_suffix(".json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(args.output.resolve())
        print(
            json.dumps(
                {
                    "named_objects": len(layout["real_names"]),
                    "regions": len(layout["region_names"]),
                    "profile": PROFILE,
                },
                ensure_ascii=False,
            )
        )
    finally:
        core.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/紫薇星图 北京 20261012200000")
    parser.add_argument(
        "--output", type=Path, default=DATA_DIR / "ziwei-validation/atlas/beijing.png"
    )
    asyncio.run(preview(parser.parse_args()))


if __name__ == "__main__":
    main()
