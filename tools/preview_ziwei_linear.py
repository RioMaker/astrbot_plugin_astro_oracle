"""显式保存 /紫微星图 的 Linear 本地预览；群内请求不走本脚本。"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from local_core.engine import PlanetEngine
from local_core.resources import DATA_DIR, prepare_all
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_correspondence import build_correspondence
from local_core.ziwei_linear import PROFILE, render_ziwei_linear
from local_core.ziwei_linear_theme import CJK, INTER


async def preview(args):
    await prepare_all(DATA_DIR)
    core = PlanetEngine(DATA_DIR)
    try:
        data = compute_ziwei(SkyChartEngine(core), args.input)
        comparison = build_correspondence(data)
        png, layout = render_ziwei_linear(data, comparison)
        root = Path(__file__).parents[1]
        names = (
            "ziwei_linear.py",
            "ziwei_linear_theme.py",
            "ziwei_names.py",
            "ziwei_correspondence.py",
            "ziwei_traditional.py",
            "ziwei_chart.py",
        )
        payload = {
            "profile": PROFILE,
            "request": args.input,
            "data": data,
            "comparison": comparison,
            "label_layout": layout,
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "font_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (INTER, CJK)
            },
            "code_sha256": {
                name: hashlib.sha256((root / "local_core" / name).read_bytes()).hexdigest()
                for name in names
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
                {"named_objects": len(layout["real_names"]), "profile": PROFILE}, ensure_ascii=False
            )
        )
    finally:
        core.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/紫微星图 北京 20261012200000")
    parser.add_argument(
        "--output", type=Path, default=DATA_DIR / "ziwei-validation/linear/beijing.png"
    )
    asyncio.run(preview(parser.parse_args()))


if __name__ == "__main__":
    main()
