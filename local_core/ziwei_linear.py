"""独立 /紫微星图：传统落宫、真实高度方位与映射依据分列。"""

import io
import math
from datetime import datetime

from PIL import Image, ImageDraw

from .image_renderer import SCALE, visual_style
from .ziwei_chart import MAJOR_ORDER, compute_ziwei
from .ziwei_correspondence import build_correspondence
from .ziwei_linear_theme import ACCENT, BG, INK, LINE, MUTED, box, rule, text
from .ziwei_names import CENTER, PANEL, RADIUS, name_layout

PROFILE = "linear-ziwei-observer-v2"
WIDTH, HEIGHT = 2440, 1810
SKY_ORIGIN = (1200, 186)
ORDER = (*MAJOR_ORDER, "禄存", "文曲", "左辅")
SQUARE = {
    "巳": (0, 0),
    "午": (1, 0),
    "未": (2, 0),
    "申": (3, 0),
    "辰": (0, 1),
    "酉": (3, 1),
    "卯": (0, 2),
    "戌": (3, 2),
    "寅": (0, 3),
    "丑": (1, 3),
    "子": (2, 3),
    "亥": (3, 3),
}


def named_rows(comparison):
    return [
        {**r, "number": f"{ORDER.index(r['name']) + 1:02d}"}
        for r in sorted(comparison["rows"], key=lambda r: ORDER.index(r["name"]))
    ]


def draw_traditional(draw, comparison, rows):
    trad = comparison["traditional"]
    mapped = {r["name"]: r for r in rows}
    layout = []
    for branch, (col, line) in SQUARE.items():
        x, y, size = 52 + col * 262, 236 + line * 262, 262
        cell = [x, y, x + size, y + size]
        box(draw, cell, radius=0)
        if branch in {trad["life_branch"], trad["body_branch"]}:
            box(draw, cell, radius=0, outline=ACCENT)
        title = f"{trad['palace_names'][branch]} · {trad['palace_stems'][branch]}{branch}"
        text(draw, (x + 14, y + 14), title, 23, strong=True)
        if branch == trad["body_branch"]:
            text(draw, (x + 236, y + 19), "身", 16, MUTED)
        layout.append(
            {
                "key": f"palace:{branch}",
                "kind": "palace",
                "branch": branch,
                "box": [x + 12, y + 10, x + 250, y + 43],
                "cell_box": cell,
            }
        )
        stars = [n for n, pos in trad["positions"].items() if pos["branch"] == branch]
        stars.sort(key=lambda n: ORDER.index(n) if n in mapped else 100)
        step = min(32, 184 / max(1, len(stars)))
        font_size = 21 if step >= 29 else 17 if step >= 23 else 14
        for i, name in enumerate(stars):
            sy = y + 57 + i * step
            number = mapped[name]["number"] if name in mapped else None
            text(
                draw,
                (x + 14, sy),
                f"{number} {name}" if number else f"[符] {name}",
                font_size,
                INK if name in MAJOR_ORDER else MUTED,
            )
            hua = next((h for h, n in trad["four_hua"].items() if n == name), None)
            if hua:
                text(draw, (x + 179, sy + 4), "化" + hua, 14, MUTED)
            layout.append(
                {
                    "key": mapped[name]["key"] if number else f"symbol:{name}",
                    "kind": "shared_star" if number else "symbolic",
                    "name": name,
                    "number": number,
                    "branch": branch,
                    "cell_box": cell,
                    "box": [x + 12, sy - 2, x + 250, sy + font_size + 5],
                }
            )
    lunar, bureau = trad["lunar"], trad["bureau"]
    center = 576
    labels = [
        (f"{bureau['element']}{'一二三四五六'[bureau['number'] - 1]}局", 36, INK),
        (
            f"农历 {trad['year_stem_branch']}年 {'闰' if lunar['leap'] else ''}"
            f"{lunar['month']}月{lunar['day']}日",
            22,
            MUTED,
        ),
        (f"{trad['hour_branch']}时 · {bureau['stem_branch']} · {bureau['nayin']}", 21, MUTED),
        (f"命宫 {trad['life_branch']} / 身宫 {trad['body_branch']}", 25, INK),
        ("25 个静态星曜 / 17 个共有名称", 18, MUTED),
        ("[符] 尚未采用唯一实体映射", 18, MUTED),
        ("传统安星核心，不含运限", 18, MUTED),
    ]
    for index, (value, size, color) in enumerate(labels):
        text(draw, (center, 585 + index * 46), value, size, color, anchor="mt")
    return layout


def observer_panel(rows):
    image = Image.new("RGB", (PANEL * SCALE, PANEL * SCALE), BG)
    draw = ImageDraw.Draw(image, "RGBA")

    def circle(radius, fill=None, outline=LINE):
        bounds = (
            (CENTER - radius) * SCALE,
            (CENTER - radius) * SCALE,
            (CENTER + radius) * SCALE,
            (CENTER + radius) * SCALE,
        )
        draw.ellipse(bounds, fill=fill, outline=outline, width=SCALE)

    circle(RADIUS, fill="#101012")
    circle(RADIUS / 2, fill="#171719", outline=MUTED)
    for fraction, label in (
        (1 / 6, "+60°"),
        (1 / 3, "+30°"),
        (1 / 2, "0° 地平线"),
        (2 / 3, "−30°"),
        (5 / 6, "−60°"),
    ):
        if fraction != 0.5:
            circle(RADIUS * fraction)
        text(draw, (CENTER + 8, CENTER - RADIUS * fraction + 12), label, 15, MUTED)
    for az in range(0, 360, 30):
        rad = math.radians(az)
        rule(
            draw,
            (CENTER, CENTER),
            (CENTER - RADIUS * math.sin(rad), CENTER - RADIUS * math.cos(rad)),
        )
    for xy, title in (
        ((600, 43), "北 0°"),
        ((42, 600), "东 90°"),
        ((1156, 600), "西 270°"),
        ((600, 1157), "南 180°"),
    ):
        text(draw, xy, title, 19, MUTED, anchor="mm")
    text(draw, (600, 612), "天顶", 16, MUTED, anchor="mm")
    layout = name_layout(rows)
    # 先画关联线，再画点与文字；只降低连线权重，不降低文字对比度。
    for label in layout:
        if label["leader_visible"]:
            rule(draw, *label["leader_line"], color=(161, 161, 170, 150))
    for row in rows:
        x, y = (CENTER + v * RADIUS for v in row["observer_xy"])
        radius, _ = visual_style(row["magnitude"])
        radius = max(2, radius)
        bounds = (
            (x - radius) * SCALE,
            (y - radius) * SCALE,
            (x + radius) * SCALE,
            (y + radius) * SCALE,
        )
        above = row["altitude_deg"] >= 0
        draw.ellipse(bounds, fill=INK if above else BG, outline=INK, width=SCALE)
        if row["name"] == "太阳":
            rule(draw, (x - 9, y), (x + 9, y), color=INK)
            rule(draw, (x, y - 9), (x, y + 9), color=INK)
    for label in layout:
        x1, y1, _, _ = label["box"]
        text(draw, (x1 + 5, y1 + 2), label["primary"], 22, INK, strong=True)
        text(draw, (x1 + 5, y1 + 30), label["secondary"], 16, MUTED)
    return image, layout


def render_ziwei_linear(data, comparison):
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    draw = ImageDraw.Draw(image, "RGBA")
    text(draw, (42, 26), "紫微星图", 42, strong=True)
    text(draw, (WIDTH - 42, 45), "传统落宫 / 真实观测方向", 20, MUTED, anchor="rt")
    moment = datetime.fromisoformat(data["epoch_local"])
    site = data["site"]
    text(
        draw, (42, 90), f"{site['label']} · {moment:%Y-%m-%d %H:%M:%S %z} · {data['timezone']}", 22
    )
    text(
        draw,
        (42, 127),
        f"纬度 {site['latitude']:.5f}° / 经度 {site['longitude']:.5f}° · {data['time_note']}",
        18,
        MUTED,
    )
    rule(draw, (42, 165), (WIDTH - 42, 165))
    rows = named_rows(comparison)
    traditional = draw_traditional(draw, comparison, rows)
    disk, real = observer_panel(rows)
    image.paste(disk, tuple(v * SCALE for v in SKY_ORIGIN))
    draw = ImageDraw.Draw(image, "RGBA")
    text(draw, (52, 183), "传统十二宫", 26, strong=True)
    text(draw, (1230, 183), "观测点全天星盘 · 星名就在星点附近", 25, strong=True)
    text(draw, (1230, 222), "北上东左 · 圆环 0° 是地平线", 16, MUTED)
    text(draw, (WIDTH - 40, 222), "实心：上方 / 空心：下方", 16, MUTED, anchor="rt")
    for label in real:
        label["box"] = [label["box"][i] + SKY_ORIGIN[i % 2] for i in range(4)]
        label["point_px"] = [label["point_px"][i] + SKY_ORIGIN[i] for i in range(2)]
        label["leader_line"] = [
            [p[i] + SKY_ORIGIN[i] for i in range(2)] for p in label["leader_line"]
        ]
    rule(draw, (42, 1388), (WIDTH - 42, 1388))
    text(draw, (52, 1405), "同名对应：传统落宫 / V 星等 / 实际高度与方位", 23, strong=True)
    links = []
    for index, row in enumerate(rows):
        col, line = index % 4, index // 4
        x, y = 52 + col * 596, 1452 + line * 43
        text(draw, (x, y), row["number"] + " " + row["name"], 20)
        text(
            draw,
            (x + 123, y + 2),
            row["traditional_branch"] + "·" + row["traditional_palace"],
            18,
            MUTED,
        )
        text(
            draw,
            (x + 269, y + 2),
            f"V{'~' if row['magnitude_estimated'] else ''}{row['magnitude']:+.1f} "
            f"高{row['altitude_deg']:+.1f}° 方{row['azimuth_deg']:.1f}°",
            16,
            MUTED,
        )
        links.append(
            {
                "key": row["key"],
                "number": row["number"],
                "traditional_branch": row["traditional_branch"],
                "altitude_deg": row["altitude_deg"],
                "azimuth_deg": row["azimuth_deg"],
                "box": [x - 2, y - 2, x + 582, y + 30],
            }
        )
    rule(draw, (42, 1691), (WIDTH - 42, 1691))
    notes = [
        "实体日月 / 北斗历史别名 / * 展示约定：按来源分级，不强行把地支格变成实测天区。",
        "* 紫微使用现代北极星、南斗与左辅采用当前目录约定。[符] 无采用的单体位置；"
        "斗数火星不自动等于 Mars。",
        "JPL DE440s / ESA Hipparcos；V 越小越亮，~ 为日月估算。高度无折射，"
        "地平线上方不保证肉眼可见，庙旺不等于测光。",
    ]
    for i, note in enumerate(notes):
        text(draw, (52, 1710 + i * 27), note, 16, MUTED)
    output = io.BytesIO()
    image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue(), {"traditional": traditional, "real_names": real, "links": links}


def generate_ziwei_png(sky, request, settings, now):
    data = compute_ziwei(sky, request, settings, now)
    comparison = build_correspondence(data)
    return render_ziwei_linear(data, comparison)[0]
