"""AstrBot 本地 PNG 输出；使用真实双半球数据，无浏览器或远程渲染依赖。"""

import io
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "AstroSans.otf"
SCALE = 2
STAR_NAMES = {
    "Sirius": "天狼星",
    "Polaris": "北极星",
    "Vega": "织女星",
    "Altair": "河鼓二",
    "Deneb": "天津四",
    "Betelgeuse": "参宿四",
    "Rigel": "参宿七",
    "Aldebaran": "毕宿五",
    "Arcturus": "大角星",
    "Capella": "五车二",
    "Antares": "心宿二",
    "Spica": "角宿一",
    "Pollux": "北河三",
    "Castor": "北河二",
    "Fomalhaut": "北落师门",
    "Canopus": "老人星",
    "Regulus": "轩辕十四",
}
CONSTELLATION_NAMES = {
    "Ori": "猎户座",
    "Sco": "天蝎座",
    "Cas": "仙后座",
    "UMa": "大熊座",
    "UMi": "小熊座",
    "Cyg": "天鹅座",
    "Aql": "天鹰座",
    "Lyr": "天琴座",
    "Dra": "天龙座",
    "Ari": "白羊座",
    "Tau": "金牛座",
    "Gem": "双子座",
    "Cnc": "巨蟹座",
    "Leo": "狮子座",
    "Vir": "室女座",
    "Lib": "天秤座",
    "Sgr": "人马座",
    "Cap": "摩羯座",
    "Aqr": "宝瓶座",
    "Psc": "双鱼座",
    "Oph": "蛇夫座",
    "Per": "英仙座",
    "And": "仙女座",
    "Peg": "飞马座",
    "Cru": "南十字座",
}


@lru_cache(maxsize=16)
def font(size):
    return ImageFont.truetype(io.BytesIO(FONT.read_bytes()), size * SCALE)


def visual_style(magnitude):
    """与浏览器版相同的曝光压缩；星等未知时用空心符号。"""
    if magnitude is None:
        return 2.0, 0.6
    return (
        0.65 + 3.85 / (1 + math.exp((magnitude - 0.5) / 1.5)),
        0.22 + 0.78 / (1 + math.exp((magnitude - 1.5) / 2)),
    )


def text(draw, xy, value, size, color, anchor="lt", stroke=0):
    draw.text(
        tuple(round(v * SCALE) for v in xy),
        value,
        font=font(size),
        fill=color,
        anchor=anchor,
        stroke_width=stroke * SCALE,
        stroke_fill="#0c1420",
    )


def fitted_text(draw, xy, value, size, color, max_width):
    while value and draw.textlength(value, font=font(size)) > max_width * SCALE:
        value = value[:-2] + "…" if len(value) > 2 else ""
    text(draw, xy, value, size, color)


def panel(scene, hemisphere, settings):
    width, center, radius = 800, 400, 324
    upper = hemisphere == "upper"
    image = Image.new("RGB", (width * SCALE, width * SCALE), "#0c1a25" if upper else "#151722")
    y, x = np.ogrid[: width * SCALE, : width * SCALE]
    distance = np.minimum(np.hypot(x - center * SCALE, y - center * SCALE) / (radius * SCALE), 1)
    inner = np.array((19, 39, 53) if upper else (35, 33, 51))
    outer = np.array((12, 20, 32))
    gradient = Image.fromarray((inner + distance[..., None] * (outer - inner)).astype("uint8"))
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).ellipse(
        tuple(
            v * SCALE for v in (center - radius, center - radius, center + radius, center + radius)
        ),
        fill=255,
    )
    image.paste(gradient, mask=mask)
    sky = image.copy()
    draw = ImageDraw.Draw(sky, "RGBA")

    def point(xy):
        return ((center + xy[0] * radius) * SCALE, (center + xy[1] * radius) * SCALE)

    def circle(x, y, r, **kwargs):
        r *= SCALE
        draw.ellipse((x - r, y - r, x + r, y + r), **kwargs)

    for fraction in (1 / 3, 2 / 3, 1):
        circle(
            center * SCALE,
            center * SCALE,
            radius * fraction,
            outline=(52, 84, 77, 255) if upper else (81, 68, 93, 255),
            width=SCALE,
        )
    for azimuth in range(0, 360, 30):
        angle = math.radians(azimuth)
        draw.line(
            (point((0, 0)), point((math.sin(angle), -math.cos(angle)))),
            fill=(141, 170, 170, 36),
            width=SCALE,
        )
    if settings.lines:
        for group in scene["constellations"]:
            for line in group["lines"]:
                draw.line(
                    [point(xy) for xy in line],
                    fill=(115, 157, 201, 105) if upper else (173, 140, 205, 100),
                    width=SCALE,
                    joint="curve",
                )
    for star in sorted(scene["stars"], key=lambda star: -star["magnitude"]):
        px, py = point(star["xy"])
        r, alpha = visual_style(star["magnitude"])
        if star["magnitude"] < 1:
            circle(px, py, r * 2.4, fill=(226, 235, 247, int(alpha * 18)))
        circle(px, py, r, fill=(226, 235, 247, round(alpha * 255)))
    for planet in scene["planets"]:
        px, py = point(planet["xy"])
        r, alpha = visual_style(planet["magnitude"])
        circle(px, py, max(5, r * 2.4), fill=(253, 216, 154, int(alpha * 20)))
        circle(
            px,
            py,
            r,
            **{
                "outline" if planet["magnitude"] is None else "fill": (
                    255,
                    222,
                    162,
                    round(alpha * 255),
                )
            },
        )
        circle(px, py, max(6, r + 2), outline=(243, 217, 151, 160), width=SCALE)
    for reference in scene["references"]:
        px, py = point(reference["xy"])
        circle(px, py, 6, outline=(220, 189, 113, 255), width=SCALE)
        for angle in np.arange(0, 2 * math.pi, math.pi / 4):
            draw.line(
                [
                    (px + r * SCALE * math.cos(angle), py + r * SCALE * math.sin(angle))
                    for r in (8, 11)
                ],
                fill=(220, 189, 113, 255),
                width=SCALE,
            )
    image.paste(sky, mask=mask)
    draw = ImageDraw.Draw(image, "RGBA")
    accent = "#8bd9c1" if upper else "#c1acd7"
    for xy, label in (
        ((400, 53), "北"),
        ((400, 747), "南"),
        ((47, 400), "东" if upper else "西"),
        ((753, 400), "西" if upper else "东"),
    ):
        text(draw, xy, label, 19, accent, "mm")
    text(draw, (400, 419), "天顶" if upper else "天底", 14, "#78929b", "mm")
    for altitude in (30, 60):
        text(
            draw,
            (404, 400 - radius * (90 - altitude) / 90 + 8),
            f"{'' if upper else '−'}{altitude}°",
            13,
            "#8296a6",
        )
    reserved = [(376, 408, 424, 432)]

    def label(value, xy, color, size=16, force=False):
        px, py = (v / SCALE for v in point(xy))
        w = draw.textlength(value, font=font(size)) / SCALE
        candidates = ((10, -size - 4), (10, 8), (-w - 10, -size - 4), (-w - 10, 8), (8, -size - 22))
        chosen = None
        for dx, dy in candidates:
            box = (px + dx - 2, py + dy - 2, px + dx + w + 2, py + dy + size + 4)
            if box[0] < 4 or box[2] > 796 or box[1] < 4 or box[3] > 769:
                continue
            if all(
                box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1] for b in reserved
            ):
                chosen = (px + dx, py + dy, box)
                break
        if chosen is None:
            if not force:
                return
            px, py = min(max(px + 10, 4), 796 - w), min(max(py - size - 4, 4), 748)
            chosen = (px, py, (px, py, px + w, py + size + 4))
        reserved.append(chosen[2])
        text(draw, chosen[:2], value, size, color, stroke=2)

    for planet in scene["planets"]:
        label(planet["name"], planet["xy"], "#ffe4ad", 18, True)
    for reference in scene["references"]:
        label("太阳方位", reference["xy"], "#ebd89e", 16, True)
    if settings.names:
        stars = sorted(
            (s for s in scene["stars"] if s["name"] and s["magnitude"] <= 3.3),
            key=lambda s: s["magnitude"],
        )
        for star in stars[:35]:
            label(STAR_NAMES.get(star["name"], star["name"]), star["xy"], "#c6d8ef")
    if settings.lines and settings.constellation_names:
        for group in sorted(scene["constellations"], key=lambda g: -len(g["lines"])):
            points = [xy for line in group["lines"] for xy in line]
            if len(points) >= 6:
                mean = np.mean(points, axis=0)
                label(
                    CONSTELLATION_NAMES.get(group["abbr"], group["name"]),
                    mean,
                    (142, 171, 197, 180),
                    15,
                )
    return image


def render_png(data, settings):
    image = Image.new("RGB", (1680 * SCALE, 1145 * SCALE), "#101b25")
    draw = ImageDraw.Draw(image)
    text(draw, (38, 20), "星图", 38, "#dcf0e8")
    moment = datetime.fromisoformat(data["epoch_local"])
    location = data["site"]
    stamp = moment.strftime("%Y-%m-%d %H:%M:%S %z")
    title = f"{location['label']} · {stamp} · {data['timezone']}"
    fitted_text(draw, (38, 71), title, 21, "#bcd0d1", 1580)
    meta = (
        f"纬度 {location['latitude']:.5f}° / 经度 {location['longitude']:.5f}° · "
        f"{data['time_note']}"
    )
    fitted_text(draw, (38, 103), meta, 17, "#93adb3", 1600)
    for index, hemisphere in enumerate(("upper", "lower")):
        scene = data["hemispheres"][hemisphere]
        x = 30 + index * 830
        color = "#a6dfcc" if index == 0 else "#d3bce5"
        title = "上半球 · 天顶中心 / 地平线以上" if index == 0 else "暗面 · 天底中心 / 地球遮挡"
        text(draw, (x + 14, 139), title, 20, color)
        image.paste(panel(scene, hemisphere, settings), (x * SCALE, 173 * SCALE))
        text(
            draw,
            (x + 14, 948),
            f"{len(scene['stars'])} 颗恒星 · {len(scene['planets'])} 个行星目标",
            17,
            color,
        )
    planets = [(p, hemi) for hemi, scene in data["hemispheres"].items() for p in scene["planets"]]
    for index, (planet, hemisphere) in enumerate(planets):
        magnitude = "未知" if planet["magnitude"] is None else f"{planet['magnitude']:.1f}"
        summary = (
            f"{planet['name']} · {'上' if hemisphere == 'upper' else '暗'} · "
            f"高度 {planet['altitude_deg']:.1f}° · 星等 {magnitude}"
        )
        text(draw, (38 + index % 4 * 409, 988 + index // 4 * 29), summary, 16, "#ead5ac")
    condition = {"day": "白昼", "twilight": "晨昏", "night": "夜间"}[data["sky_condition"]]
    text(
        draw,
        (38, 1051),
        f"{condition} · 太阳高度 {data['sun_altitude_deg']:.1f}° · 理想地平线、无折射；"
        "星等经曝光映射，实际可见性受日光、天气和地形影响。",
        16,
        "#9aadba",
    )
    text(
        draw,
        (38, 1080),
        "数据 ESA Hipparcos / NASA JPL DE440s / GeoNames (CC BY 4.0) · "
        "星座图形 Stellarium S&T: Paul Krizak, Jonathan E. Piskor, G. Zotti / CC BY-SA 2.0",
        14,
        "#839ba7",
    )
    text(
        draw,
        (38, 1112),
        "星座图形来源 github.com/Stellarium/stellarium/tree/master/skycultures/modern_st"
        " · 许可 creativecommons.org/licenses/by-sa/2.0/",
        12,
        "#839ba7",
    )
    output = io.BytesIO()
    image.resize((1680, 1145), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue()
