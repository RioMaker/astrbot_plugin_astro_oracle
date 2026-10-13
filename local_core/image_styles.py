"""图册版式共用真实星盘；AstrBot 使用空间观测台，其余版式供本地预览。"""

import io
from datetime import datetime

from PIL import Image, ImageDraw

from .image_renderer import SCALE, STAR_NAMES, fitted_text, panel, rectangle, rule, text

STYLES = {
    "archive": {
        "label": "A · 纸本典藏",
        "background": "#f1eadc",
        "ink": "#333f43",
        "muted": "#6e726c",
        "upper": "#986a3e",
        "lower": "#637281",
        "line": "#b7ab97",
        "surface": "#eae2d2",
    },
    "observatory": {
        "label": "B · 空间观测台",
        "background": "#08121e",
        "ink": "#e1eef8",
        "muted": "#94aec5",
        "upper": "#78e6d2",
        "lower": "#a6b7ff",
        "line": "#314a62",
        "surface": "#102337",
    },
    "gallery": {
        "label": "C · 极简画廊",
        "background": "#faf9f5",
        "ink": "#202b36",
        "muted": "#67737d",
        "upper": "#bb5435",
        "lower": "#4c6c91",
        "line": "#bbc1c4",
        "surface": "#eceeea",
    },
}
WIDTH, HEIGHT = 1760, 1510
PLANET_ORDER = ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")


def style_size(style):
    return WIDTH, 1650 if style == "observatory" else HEIGHT


def ellipse(draw, box, **kwargs):
    draw.ellipse(tuple(round(v * SCALE) for v in box), **kwargs)


def header(draw, data, theme, style):
    moment = datetime.fromisoformat(data["epoch_local"])
    stamp = moment.strftime("%Y.%m.%d  %H:%M:%S  %z")
    location = data["site"]
    coordinates = f"纬度 {location['latitude']:.5f}° / 经度 {location['longitude']:.5f}°"
    if style == "archive":
        for inset in (24, 32):
            rectangle(
                draw, (inset, inset, WIDTH - inset, HEIGHT - inset), None, theme["line"], radius=0
            )
        text(draw, (880, 58), "星 轨 神 谕  /  ASTRO ORACLE", 16, theme["upper"], "mt")
        text(draw, (880, 94), "星  图", 54, theme["ink"], "mt")
        fitted_text(draw, (60, 180), location["label"], 20, theme["ink"], 540)
        text(draw, (1700, 182), f"{stamp} · {data['timezone']}", 17, theme["muted"], "rt")
        text(draw, (60, 213), coordinates, 14, theme["muted"])
        text(draw, (1700, 213), "同一时刻 · 双半球全天图", 14, theme["muted"], "rt")
        rule(draw, (60, 248), (846, 248), theme["line"])
        rule(draw, (914, 248), (1700, 248), theme["line"])
        draw.polygon(
            [
                (880 * SCALE, 241 * SCALE),
                (887 * SCALE, 248 * SCALE),
                (880 * SCALE, 255 * SCALE),
                (873 * SCALE, 248 * SCALE),
            ],
            outline=theme["upper"],
            width=SCALE,
        )
    elif style == "observatory":
        rectangle(draw, (50, 43, 56, 208), theme["upper"], radius=0)
        text(draw, (78, 43), "ASTRO ORACLE   /   星轨神谕", 15, theme["upper"])
        text(draw, (74, 79), "星图", 68, theme["ink"])
        fitted_text(draw, (78, 168), location["label"], 24, theme["ink"], 720)
        text(draw, (78, 210), coordinates, 15, theme["muted"])
        text(draw, (1700, 48), moment.strftime("%Y.%m.%d"), 35, theme["ink"], "rt")
        text(draw, (1700, 98), moment.strftime("%H:%M:%S  %z"), 23, theme["upper"], "rt")
        text(draw, (1700, 137), data["timezone"], 16, theme["muted"], "rt")
        text(draw, (1700, 210), "同一时刻 · 双半球全天图", 15, theme["muted"], "rt")
        rule(draw, (50, 248), (1710, 248), theme["line"])
        rule(draw, (50, 248), (265, 248), theme["upper"], 2)
    else:
        text(draw, (56, 50), "星图", 82, theme["ink"])
        text(draw, (62, 153), "星轨神谕  /  ASTRO ORACLE", 16, theme["muted"])
        ellipse(draw, (1537, 55, 1617, 135), fill=theme["upper"])
        ellipse(draw, (1577, 75, 1637, 135), outline=theme["ink"], width=2 * SCALE)
        fitted_text(draw, (62, 203), location["label"], 23, theme["ink"], 520)
        text(draw, (1700, 160), f"{stamp} · {data['timezone']}", 18, theme["ink"], "rt")
        text(draw, (1700, 205), coordinates, 15, theme["muted"], "rt")
        rule(draw, (60, 248), (1700, 248), theme["ink"], 2)


def plots(image, data, settings, theme, style):
    draw = ImageDraw.Draw(image, "RGBA")
    for index, hemisphere in enumerate(("upper", "lower")):
        x = 50 + index * 860
        accent = theme["upper"] if index == 0 else theme["lower"]
        title = "上半球" if index == 0 else "暗面"
        description = "天顶中心 · 地平线以上" if index == 0 else "天底中心 · 地球遮挡"
        if style == "archive":
            text(draw, (x + 400, 276), f"{title}  /  {description}", 17, theme["ink"], "mt")
        else:
            text(draw, (x + 12, 275), f"0{index + 1}", 16, accent)
            text(draw, (x + 51, 271), title, 24, theme["ink"])
            text(draw, (x + 166, 281), description, 15, theme["muted"])
        scene = data["hemispheres"][hemisphere]
        image.paste(panel(scene, hemisphere, settings, frame=theme), (x * SCALE, 316 * SCALE))
        text(
            draw,
            (x + 400, 1105),
            f"{len(scene['stars']):,} 颗恒星 · {len(scene['planets'])} 个行星目标",
            15,
            accent,
            "mt",
        )
        if style == "observatory":
            for a, b, c in (
                ((x + 1, 308), (x + 1, 330), (x + 23, 308)),
                ((x + 799, 308), (x + 799, 330), (x + 777, 308)),
                ((x + 1, 1140), (x + 1, 1118), (x + 23, 1140)),
                ((x + 799, 1140), (x + 799, 1118), (x + 777, 1140)),
            ):
                rule(draw, a, b, accent)
                rule(draw, a, c, accent)


def legend(draw, data, settings, theme):
    y = 1153
    text(draw, (60, y), "读图", 14, theme["ink"], "lm")
    for x, kind, caption in (
        (148, "star", "恒星"),
        (274, "planet", "行星"),
        (409, "sun", "太阳方位"),
        (600, "line", "星座连线"),
    ):
        if kind == "line":
            if not settings.lines:
                continue
            rule(draw, (x, y), (x + 26, y), theme["muted"])
        else:
            r = 3 if kind == "star" else 6
            ellipse(
                draw,
                (x - r, y - r, x + r, y + r),
                fill=theme["ink"] if kind == "star" else None,
                outline=theme["upper"] if kind != "star" else None,
                width=SCALE,
            )
            if kind == "sun":
                rule(draw, (x - 10, y), (x + 10, y), theme["upper"])
                rule(draw, (x, y - 10), (x, y + 10), theme["upper"])
        text(draw, (x + 34, y), caption, 14, theme["muted"], "lm")
    condition = {"day": "白昼", "twilight": "晨昏", "night": "夜间"}[data["sky_condition"]]
    text(
        draw,
        (1700, y),
        f"{condition} · 太阳高度 {data['sun_altitude_deg']:+.1f}°",
        16,
        theme["ink"],
        "rm",
    )


def planet_strip(draw, data, theme, style):
    planets = sorted(
        [(p, hemi) for hemi, scene in data["hemispheres"].items() for p in scene["planets"]],
        key=lambda item: PLANET_ORDER.index(item[0]["key"]),
    )
    if style == "gallery":
        rectangle(draw, (60, 1194, 1700, 1364), theme["surface"], radius=0)
        text(draw, (84, 1211), f"{len(planets):02}", 68, theme["upper"])
        text(draw, (90, 1304), "行星目标", 17, theme["ink"])
        for index, (planet, hemi) in enumerate(planets):
            x = 340 + index % 4 * 335
            y = 1211 + index // 4 * 75
            accent = theme["upper"] if hemi == "upper" else theme["lower"]
            text(draw, (x, y), planet["name"], 22, theme["ink"])
            text(draw, (x + 95, y + 6), "上半球" if hemi == "upper" else "暗面", 12, accent)
            magnitude = "未知" if planet["magnitude"] is None else f"{planet['magnitude']:.1f}"
            text(
                draw,
                (x, y + 34),
                f"高度 {planet['altitude_deg']:+.1f}° / 星等 {magnitude}",
                14,
                theme["muted"],
            )
    else:
        rule(draw, (60, 1190), (1700, 1190), theme["line"])
        text(draw, (60, 1207), "行星位置", 17, theme["ink"])
        text(draw, (1700, 1210), "高度以地平线为 0° · 星等数值越小越亮", 13, theme["muted"], "rt")
        for index, (planet, hemi) in enumerate(planets):
            x = 60 + index * 237
            accent = theme["upper"] if hemi == "upper" else theme["lower"]
            if index > 0:
                rule(draw, (x - 11, 1245), (x - 11, 1352), theme["line"])
            text(draw, (x + 14, 1254), planet["name"], 23, theme["ink"])
            text(draw, (x + 202, 1261), "上" if hemi == "upper" else "暗", 13, accent, "rt")
            text(draw, (x + 14, 1296), f"高度 {planet['altitude_deg']:+.1f}°", 16, theme["muted"])
            magnitude = "未知" if planet["magnitude"] is None else f"{planet['magnitude']:.1f}"
            text(draw, (x + 14, 1324), f"星等 {magnitude}", 14, theme["muted"])


def summary_entries(data, limit=12):
    """只读取当前星等筛选后的真实数据；恒星按亮度排序，不要求有通用名。"""
    result = {}
    for hemisphere in ("upper", "lower"):
        scene = data["hemispheres"][hemisphere]
        planets = sorted(scene["planets"], key=lambda p: PLANET_ORDER.index(p["key"]))
        stars = sorted(scene["stars"], key=lambda s: (s["magnitude"], s["hip"]))[:limit]
        result[hemisphere] = [("planet", p) for p in planets] + [("star", s) for s in stars]
    return result


def observatory_summary(draw, data, settings, theme):
    rule(draw, (60, 1190), (1700, 1190), theme["line"])
    text(draw, (60, 1209), "天体速览", 19, theme["ink"])
    text(
        draw,
        (1700, 1213),
        "恒星按星等选取 · 数值越小越亮 · 方位北 0° / 东 90°",
        13,
        theme["muted"],
        "rt",
    )
    entries = summary_entries(data)
    for index, hemisphere in enumerate(("upper", "lower")):
        x = 60 + index * 860
        accent = theme["upper"] if index == 0 else theme["lower"]
        targets = entries[hemisphere]
        planets = sum(kind == "planet" for kind, _ in targets)
        stars = len(targets) - planets
        side = "上半球" if index == 0 else "暗面"
        text(draw, (x, 1247), f"{side} · {planets} 个行星 / {stars} 颗亮星", 15, accent)
        rows = max(1, (len(targets) + 1) // 2)
        for column in range(2):
            left = x + column * 408
            for offset, heading in (
                (0, "天体"),
                (211, "HIP"),
                (259, "星等"),
                (319, "高度°"),
                (383, "方位°"),
            ):
                text(
                    draw,
                    (left + offset, 1280),
                    heading,
                    12,
                    theme["muted"],
                    "lt" if offset == 0 else "rt",
                )
            rule(draw, (left, 1300), (left + 383, 1300), theme["line"])
            for row, (kind, target) in enumerate(targets[column * rows : (column + 1) * rows]):
                y = 1310 + row * 27
                if kind == "planet":
                    name, identifier, color = target["name"], "—", "#ffe4ad"
                else:
                    name = STAR_NAMES.get(target["name"], target["name"] or "未命名")
                    name = name if settings.names else "恒星"
                    identifier, color = str(target["hip"]), theme["ink"]
                fitted_text(draw, (left, y), name, 15, color, 144)
                text(draw, (left + 211, y + 2), identifier, 12, theme["muted"], "rt")
                magnitude = "未知" if target["magnitude"] is None else f"{target['magnitude']:.1f}"
                text(draw, (left + 259, y), magnitude, 15, color, "rt")
                text(
                    draw,
                    (left + 319, y),
                    f"{target['altitude_deg']:+.1f}",
                    15,
                    theme["muted"],
                    "rt",
                )
                text(
                    draw, (left + 383, y), f"{target['azimuth_deg']:.1f}", 15, theme["muted"], "rt"
                )
                rule(draw, (left, y + 22), (left + 383, y + 22), (49, 74, 98, 65))
        if not targets:
            text(draw, (x, 1310), "当前筛选下无天体", 15, theme["muted"])


def footer(draw, data, theme, top=1384):
    rule(draw, (60, top), (1700, top), theme["line"])
    fitted_text(draw, (60, top + 17), data["time_note"], 14, theme["ink"], 1640)
    text(
        draw,
        (60, top + 42),
        "理想地平线 · 无大气折射 · 星等经曝光映射；实际可见性受日光、天气和地形影响。",
        13,
        theme["muted"],
    )
    text(
        draw,
        (60, top + 61),
        "数据 ESA Hipparcos / NASA JPL DE440s / GeoNames (CC BY 4.0) · 星座图形 Stellarium S&T: "
        "Paul Krizak, Jonathan E. Piskor, G. Zotti / CC BY-SA 2.0",
        11,
        theme["muted"],
    )
    text(
        draw,
        (60, top + 78),
        "星座图形来源 github.com/Stellarium/stellarium/tree/master/skycultures/modern_st"
        " · 许可 creativecommons.org/licenses/by-sa/2.0/",
        10,
        theme["muted"],
    )


def render_style_png(data, settings, style):
    """独立预览入口；仅根据已计算结果绘图，不保存或修改数据。"""
    theme = STYLES[style]
    width, height = style_size(style)
    image = Image.new("RGB", (width * SCALE, height * SCALE), theme["background"])
    draw = ImageDraw.Draw(image, "RGBA")
    header(draw, data, theme, style)
    plots(image, data, settings, theme, style)
    legend(draw, data, settings, theme)
    if style == "observatory":
        observatory_summary(draw, data, settings, theme)
        footer(draw, data, theme, top=1540)
    else:
        planet_strip(draw, data, theme, style)
        footer(draw, data, theme)
    output = io.BytesIO()
    image.resize((width, height), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue()
