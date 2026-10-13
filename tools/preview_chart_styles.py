"""固定同一真实时地生成三种版式与对照图，产物仅写入被忽略的 data。"""

import argparse
import asyncio
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw

from local_core.bot_commands import ChartSettings, parse_request, resolve_place, resolve_time
from local_core.engine import PlanetEngine
from local_core.image_renderer import SCALE, panel, render_png, text
from local_core.image_styles import STYLES, render_style_png, style_size, summary_entries
from local_core.resources import DATA_DIR, prepare_all
from local_core.sky_chart import SkyChartEngine

OUTPUT = DATA_DIR / "style-preview"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="北京 20261010203000")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    settings = ChartSettings()
    request = parse_request(args.input)
    asyncio.run(prepare_all(DATA_DIR))
    core = PlanetEngine(DATA_DIR)
    try:
        sky = SkyChartEngine(core)
        site, zone, source = resolve_place(
            sky.places, request.place_text or settings.default_place, settings.coordinate_timezone
        )
        zone = request.timezone_override or zone
        moment, note = resolve_time(
            request, zone, settings.default_time, datetime.now(timezone.utc)
        )
        data = sky.compute(moment.isoformat(), site, zone, settings.magnitude_limit)
        data.update(time_note=note, timezone=zone, site_source=source)
        (OUTPUT / "original.png").write_bytes(render_png(data, settings))

        # 圆盘内部像素一致，外围配色不改变真实星点、连线与标注。
        y, x = np.ogrid[: 800 * SCALE, : 800 * SCALE]
        interior = (x - 400 * SCALE) ** 2 + (y - 400 * SCALE) ** 2 < (322 * SCALE) ** 2
        for hemisphere in ("upper", "lower"):
            scene = data["hemispheres"][hemisphere]
            original = np.asarray(panel(scene, hemisphere, settings))
            for theme in STYLES.values():
                candidate = np.asarray(panel(scene, hemisphere, settings, theme))
                assert np.array_equal(original[interior], candidate[interior])
        for style in STYLES:
            path = OUTPUT / f"{style}.png"
            path.write_bytes(render_style_png(data, settings, style))
            print(path.resolve())
        for hemisphere, targets in summary_entries(data).items():
            stars = [target for kind, target in targets if kind == "star"]
            source_stars = data["hemispheres"][hemisphere]["stars"]
            assert len(stars) == min(12, len(source_stars))
            if stars:
                selected = {s["hip"] for s in stars}
                faintest = max(s["magnitude"] for s in stars)
                assert all(
                    s["magnitude"] >= faintest for s in source_stars if s["hip"] not in selected
                )
            assert all(
                target in data["hemispheres"][hemisphere]["stars" if kind == "star" else "planets"]
                for kind, target in targets
            )
        print("PASS: compact table includes actual brightest stars and unchanged coordinates.")
        print("PASS: same real-data scene; star-disc interior pixels match in all three styles.")
    finally:
        core.close()

    contact = Image.new("RGB", (1800, 640), "#dfe3e7")
    for index, (style, theme) in enumerate(STYLES.items()):
        with Image.open(OUTPUT / f"{style}.png") as preview:
            assert preview.size == style_size(style) and preview.format == "PNG"
            preview.thumbnail((580, 544), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (580, 544), theme["background"])
            tile.paste(preview, ((580 - preview.width) // 2, 0))
            contact.paste(tile, (10 + index * 600, 86))
        label = Image.new("RGB", (1160, 132), theme["background"])
        draw = ImageDraw.Draw(label)
        text(draw, (20, 19), theme["label"], 25, theme["ink"])
        contact.paste(label.resize((580, 66), Image.Resampling.LANCZOS), (10 + index * 600, 10))
    contact.save(OUTPUT / "comparison.png")
    print((OUTPUT / "comparison.png").resolve())


if __name__ == "__main__":
    main()
