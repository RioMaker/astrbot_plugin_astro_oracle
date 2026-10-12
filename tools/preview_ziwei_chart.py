"""仅本地生成紫微星名新图，复用 /星图 输入；不接入或发送 AstrBot 消息。"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from local_core.bot_commands import ChartSettings
from local_core.engine import PlanetEngine
from local_core.resources import DATA_DIR, prepare_all
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_single_renderer import render_ziwei_png


async def preview(args):
    await prepare_all(DATA_DIR)
    core = PlanetEngine(DATA_DIR)
    try:
        sky = SkyChartEngine(core)
        data = compute_ziwei(sky, args.input, ChartSettings(default_time=args.default_time))
        png, layout = render_ziwei_png(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(png)
        audit = {
            "request": args.input,
            "data": data,
            "label_layout": layout,
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "code_sha256": {
                name: hashlib.sha256(
                    (Path(__file__).resolve().parents[1] / "local_core" / name).read_bytes()
                ).hexdigest()
                for name in (
                    "ziwei_chart.py",
                    "ziwei_palaces.py",
                    "ziwei_photometry.py",
                    "ziwei_single_renderer.py",
                    "ziwei_palace_display.py",
                )
            },
        }
        args.output.with_suffix(".json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(args.output.resolve())
        print(
            json.dumps(
                {
                    "main": sum(
                        o["major"] for s in data["hemispheres"].values() for o in s["objects"]
                    ),
                    "objects": sum(len(s["objects"]) for s in data["hemispheres"].values()),
                    "palaces": len(data["palace_layer"]["sectors"]),
                    "symbolic_malefics": len(data["palace_layer"]["symbolic_malefics"]),
                }
            )
        )
    finally:
        core.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/星图 北京 20261012200000")
    parser.add_argument("--default-time", default="08:00:00")
    parser.add_argument(
        "--output", type=Path, default=DATA_DIR / "ziwei-validation" / "beijing.png"
    )
    asyncio.run(preview(parser.parse_args()))


if __name__ == "__main__":
    main()
