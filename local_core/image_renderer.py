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
BACKGROUND = "#0b1422"
UPPER_ACCENT = "#dbbd86"
LOWER_ACCENT = "#acb7df"
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


def rule(draw, start, end, color, width=1):
    draw.line(
        [tuple(round(v * SCALE) for v in xy) for xy in (start, end)],
        fill=color,
        width=width * SCALE,
    )


def rectangle(draw, box, fill, outline=None, radius=12):
    draw.rounded_rectangle(
        tuple(round(v * SCALE) for v in box),
        radius=radius * SCALE,
        fill=fill,
        outline=outline,
        width=SCALE,
    )


def panel(scene, hemisphere, settings, frame=None):
    width, center, radius = 800, 400, 324
    upper = hemisphere == "upper"
    image = Image.new(
        "RGB", (width * SCALE, width * SCALE), frame["background"] if frame else BACKGROUND
    )
    y, x = np.ogrid[: width * SCALE, : width * SCALE]
    distance = np.minimum(np.hypot(x - center * SCALE, y - center * SCALE) / (radius * SCALE), 1)
    inner = np.array((20, 38, 58) if upper else (27, 30, 51))
    outer = np.array((9, 19, 34))
    gradient = Image.fromarray(
        (inner + distance[..., None] ** 1.4 * (outer - inner)).astype("uint8")
    )
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
            outline=(146, 160, 184, 44),
            width=SCALE,
        )
    for azimuth in range(0, 360, 30):
        angle = math.radians(azimuth)
        draw.line(
            (point((0, 0)), point((math.sin(angle), -math.cos(angle)))),
            fill=(141, 170, 190, 25),
            width=SCALE,
        )
    if settings.lines:
        for group in scene["constellations"]:
            for line in group["lines"]:
                draw.line(
                    [point(xy) for xy in line],
                    fill=(114, 161, 209, 115) if upper else (150, 146, 207, 105),
                    width=SCALE,
                    joint="curve",
                )
    for star in sorted(scene["stars"], key=lambda star: -star["magnitude"]):
        px, py = point(star["xy"])
        r, alpha = visual_style(star["magnitude"])
        if star["magnitude"] < 1:
            for factor, opacity in ((3.5, 8), (2.4, 16), (1.5, 26)):
                circle(px, py, r * factor, fill=(211, 230, 255, int(alpha * opacity)))
        if star["magnitude"] < 0.5:
            extent = r * 2.5 * SCALE
            draw.line((px - extent, py, px + extent, py), fill=(214, 233, 255, 65), width=SCALE)
            draw.line((px, py - extent, px, py + extent), fill=(214, 233, 255, 65), width=SCALE)
        circle(px, py, r, fill=(226, 235, 247, round(alpha * 255)))
    for planet in scene["planets"]:
        px, py = point(planet["xy"])
        r, alpha = visual_style(planet["magnitude"])
        for factor, opacity in ((4, 9), (2.4, 22)):
            circle(px, py, max(5, r * factor), fill=(253, 216, 154, int(alpha * opacity)))
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
    accent = (
        (frame["upper"] if upper else frame["lower"])
        if frame
        else (UPPER_ACCENT if upper else LOWER_ACCENT)
    )
    # 刻度属于方位仪表；真实天体与星座线始终裁剪在地平线内。
    for ring_radius, color in (
        (radius, (181, 188, 201, 120)),
        (346, frame["line"] if frame else (141, 157, 183, 65)),
    ):
        draw.ellipse(
            tuple(
                v * SCALE
                for v in (
                    400 - ring_radius,
                    400 - ring_radius,
                    400 + ring_radius,
                    400 + ring_radius,
                )
            ),
            outline=color,
            width=SCALE,
        )
    for azimuth in range(0, 360, 5):
        angle = math.radians(azimuth)
        major = azimuth % 30 == 0
        radii = (332, 343) if major else (337, 343)
        rule(
            draw,
            (400 + radii[0] * math.sin(angle), 400 - radii[0] * math.cos(angle)),
            (400 + radii[1] * math.sin(angle), 400 - radii[1] * math.cos(angle)),
            (accent if major else frame["line"])
            if frame
            else ((219, 189, 134, 160) if upper and major else (149, 168, 199, 105)),
        )
    for xy, label in (
        ((400, 32), "北 N"),
        ((400, 766), "南 S"),
        ((31, 400), "东" if upper else "西"),
        ((769, 400), "西" if upper else "东"),
    ):
        text(draw, xy, label, 17, accent, "mm")
    rule(draw, (394, 400), (406, 400), (166, 183, 209, 100))
    rule(draw, (400, 394), (400, 406), (166, 183, 209, 100))
    text(draw, (400, 419), "天顶" if upper else "天底", 12, "#7a8da8", "mm")
    for altitude in (30, 60):
        text(
            draw,
            (404, 400 - radius * (90 - altitude) / 90 + 8),
            f"{'' if upper else '−'}{altitude}°",
            13,
            "#8296a6",
        )
    reserved = [
        (373, 392, 427, 432),
        (366, 14, 434, 49),
        (366, 748, 434, 784),
        (12, 382, 50, 418),
        (750, 382, 788, 418),
    ]

    def label(value, xy, color, size=16, force=False):
        px, py = (v / SCALE for v in point(xy))
        w = draw.textlength(value, font=font(size)) / SCALE
        candidates = (
            (10, -size - 4),
            (10, 8),
            (-w - 10, -size - 4),
            (-w - 10, 8),
            (8, -size - 22),
            (-w / 2, 16),
            (-w / 2, -size - 16),
        )
        chosen = None
        for dx, dy in candidates:
            box = (px + dx - 2, py + dy - 2, px + dx + w + 2, py + dy + size + 4)
            if box[0] < 4 or box[2] > 796 or box[1] < 4 or box[3] > 769:
                continue
            if not force and any(
                math.hypot(bx - center, by - center) > radius - 4
                for bx in (box[0], box[2])
                for by in (box[1], box[3])
            ):
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
            (
                s
                for s in scene["stars"]
                if s["name"]
                and s["magnitude"] <= 3.3
                and (s["name"] in STAR_NAMES or s["magnitude"] <= 1.2)
            ),
            key=lambda s: (s["name"] not in STAR_NAMES, s["magnitude"]),
        )
        for star in stars[:20]:
            label(STAR_NAMES.get(star["name"], star["name"]), star["xy"], "#c6d8ef")
    if settings.lines and settings.constellation_names:
        groups = sorted(
            (g for g in scene["constellations"] if g["abbr"] in CONSTELLATION_NAMES),
            key=lambda g: -len(g["lines"]),
        )
        for group in groups[:16]:
            points = [xy for line in group["lines"] for xy in line]
            if len(points) >= 6:
                mean = np.mean(points, axis=0)
                label(
                    CONSTELLATION_NAMES.get(group["abbr"], group["name"]),
                    mean,
                    (133, 157, 189, 180),
                    14,
                )
    return image


def render_png(data, settings):
    image = Image.new("RGB", (1680 * SCALE, 1270 * SCALE), BACKGROUND)
    draw = ImageDraw.Draw(image, "RGBA")
    text(draw, (38, 17), "星轨神谕", 13, UPPER_ACCENT)
    text(draw, (36, 41), "星图", 44, "#eef1f7")
    rule(draw, (160, 29), (160, 88), "#354257")
    moment = datetime.fromisoformat(data["epoch_local"])
    location = data["site"]
    fitted_text(draw, (186, 29), location["label"], 22, "#e0e7f1", 1080)
    stamp = moment.strftime("%Y.%m.%d  %H:%M:%S  %z")
    fitted_text(draw, (186, 62), f"{stamp} · {data['timezone']}", 18, "#a2b3cc", 1080)
    text(draw, (1640, 28), "ASTRO ORACLE", 15, UPPER_ACCENT, "rt")
    text(draw, (1640, 58), "同一时刻 · 双半球全天图", 14, "#8b9eb9", "rt")
    meta = (
        f"纬度 {location['latitude']:.5f}° / 经度 {location['longitude']:.5f}° · "
        f"{data['time_note']}"
    )
    fitted_text(draw, (38, 104), meta, 15, "#8598b3", 1604)
    rule(draw, (38, 131), (1642, 131), "#2e3a4d")
    for index, hemisphere in enumerate(("upper", "lower")):
        scene = data["hemispheres"][hemisphere]
        x = 30 + index * 830
        color = UPPER_ACCENT if index == 0 else LOWER_ACCENT
        text(draw, (x + 14, 146), "01" if index == 0 else "02", 15, color)
        text(draw, (x + 48, 141), "上半球" if index == 0 else "暗面", 23, "#e0e7f1")
        text(
            draw,
            (x + 155, 148),
            "天顶中心 · 地平线以上" if index == 0 else "天底中心 · 地球遮挡",
            15,
            "#879cb9",
        )
        image.paste(panel(scene, hemisphere, settings), (x * SCALE, 173 * SCALE))
        text(
            draw,
            (x + 400, 962),
            f"{len(scene['stars'])} 颗恒星 · {len(scene['planets'])} 个行星目标",
            15,
            color,
            "mt",
        )

    # 图例只解释符号，不向真实星空加入装饰星点。
    text(draw, (38, 989), "读图", 14, UPPER_ACCENT, "lm")
    for x, kind, caption in (
        (119, "star", "恒星"),
        (240, "planet", "行星"),
        (365, "sun", "太阳方位"),
        (540, "line", "星座连线"),
    ):
        if kind == "line":
            rule(draw, (x, 989), (x + 25, 989), "#7198c2")
        else:
            r = 3 if kind == "star" else 6
            draw.ellipse(
                tuple(v * SCALE for v in (x - r, 989 - r, x + r, 989 + r)),
                fill="#dbe8fa" if kind == "star" else None,
                outline=UPPER_ACCENT if kind != "star" else None,
                width=SCALE,
            )
            if kind == "sun":
                rule(draw, (x - 10, 989), (x + 10, 989), UPPER_ACCENT)
                rule(draw, (x, 979), (x, 999), UPPER_ACCENT)
        text(draw, (x + 35, 989), caption, 14, "#a0b0c7", "lm")
    condition = {"day": "白昼", "twilight": "晨昏", "night": "夜间"}[data["sky_condition"]]
    text(
        draw,
        (1642, 989),
        f"{condition} · 太阳高度 {data['sun_altitude_deg']:+.1f}°",
        15,
        "#bbc7dc",
        "rm",
    )
    rule(draw, (38, 1013), (1642, 1013), "#2e3a4d")
    text(draw, (38, 1030), "行星位置", 17, "#dce4f1")
    text(draw, (1642, 1032), "高度以地平线为 0° · 星等数值越小越亮", 13, "#899cb8", "rt")
    order = {
        name: index
        for index, name in enumerate(
            ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")
        )
    }
    planets = sorted(
        [(p, hemi) for hemi, scene in data["hemispheres"].items() for p in scene["planets"]],
        key=lambda item: order[item[0]["key"]],
    )
    for index, (planet, hemisphere) in enumerate(planets):
        x = 38 + index * 231
        color = UPPER_ACCENT if hemisphere == "upper" else LOWER_ACCENT
        rectangle(draw, (x, 1060, x + 218, 1154), "#111f32", "#2b3b52")
        rule(draw, (x + 14, 1077), (x + 14, 1096), color, 2)
        text(draw, (x + 25, 1075), planet["name"], 21, "#e8edf6")
        text(draw, (x + 203, 1084), "上" if hemisphere == "upper" else "暗", 13, color, "rm")
        magnitude = "未知" if planet["magnitude"] is None else f"{planet['magnitude']:.1f}"
        text(draw, (x + 15, 1111), f"高度 {planet['altitude_deg']:+.1f}°", 15, "#aabbd2")
        text(draw, (x + 15, 1133), f"星等 {magnitude}", 13, "#8398b6")
    rule(draw, (38, 1177), (1642, 1177), "#2e3a4d")
    text(
        draw,
        (38, 1192),
        "理想地平线 · 无大气折射 · 星等经曝光映射；实际可见性受日光、天气和地形影响。",
        14,
        "#9aacc5",
    )
    text(
        draw,
        (38, 1218),
        "数据 ESA Hipparcos / NASA JPL DE440s / GeoNames (CC BY 4.0) · "
        "星座图形 Stellarium S&T: Paul Krizak, Jonathan E. Piskor, G. Zotti / CC BY-SA 2.0",
        12,
        "#7589a5",
    )
    text(
        draw,
        (38, 1241),
        "星座图形来源 github.com/Stellarium/stellarium/tree/master/skycultures/modern_st"
        " · 许可 creativecommons.org/licenses/by-sa/2.0/",
        11,
        "#7589a5",
    )
    output = io.BytesIO()
    image.resize((1680, 1270), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue()
