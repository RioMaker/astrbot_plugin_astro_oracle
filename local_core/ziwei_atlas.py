"""聊天 PNG：真实全天方向、球面关联区域与传统宫内说明。"""

import io
import math
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

from .image_renderer import SCALE, visual_style
from .ziwei_association import FORMULA, LIMITATION, boundary_mask, region_map
from .ziwei_association import PROFILE as ASSOCIATION_PROFILE
from .ziwei_chart import MAJOR_ORDER
from .ziwei_linear import ORDER, SQUARE, named_rows
from .ziwei_linear_theme import BG, CJK, INK, INTER, LINE, MUTED, box, measure, rule, text
from .ziwei_names import CENTER, PANEL, RADIUS, free_box, name_layout, segment_hits_box
from .ziwei_palaces import BRANCHES

PROFILE = "linear-ziwei-association-atlas-v1"
WIDTH, HEIGHT = 2440, 1810
SKY_ORIGIN = (24, 210)
PALACE_ORIGIN, CELL = (1320, 262), 250
LAVENDER = "#a5adff"


def _fit(draw, xy, value, size, max_width, color=INK, **kwargs):
    while measure(value, size) > max_width and size > 12:
        size -= 1
    text(draw, xy, value, size, color, **kwargs)


def _offset_layout(labels, origin):
    for label in labels:
        label["box"] = [v + origin[i % 2] for i, v in enumerate(label["box"])]
        for key in ("point_px",):
            if key in label:
                label[key] = [v + origin[i] for i, v in enumerate(label[key])]
        if "leader_line" in label:
            label["leader_line"] = [
                [v + origin[i] for i, v in enumerate(p)] for p in label["leader_line"]
            ]


def palace_grid(draw, comparison, rows):
    trad, labels = comparison["traditional"], []
    mapped = {r["name"]: r for r in rows}
    ox, oy = PALACE_ORIGIN
    for branch, (col, line) in SQUARE.items():
        x, y = ox + col * CELL, oy + line * CELL
        cell = [x + 4, y + 4, x + CELL - 4, y + CELL - 4]
        life, body = branch == trad["life_branch"], branch == trad["body_branch"]
        box(draw, cell, fill="#171823" if life else "#111113", outline=LAVENDER if life else LINE)
        text(draw, (x + 20, y + 20), branch, 31, LAVENDER if life else INK, strong=True)
        text(draw, (x + 64, y + 23), trad["palace_names"][branch], 25, strong=True)
        if body:
            text(draw, (x + CELL - 24, y + 28), "身", 17, LAVENDER, anchor="rt")
        rule(draw, (x + 20, y + 65), (x + CELL - 20, y + 65))
        labels.append(
            {
                "kind": "palace",
                "branch": branch,
                "box": [x + 17, y + 16, x + CELL - 16, y + 56],
                "cell_box": cell,
            }
        )
        stars = [n for n, p in trad["positions"].items() if p["branch"] == branch]
        stars.sort(key=lambda n: ORDER.index(n) if n in mapped else 100)
        step = min(30, 151 / max(1, len(stars)))
        size = 21 if step >= 27 else 17 if step >= 22 else 16 if step >= 21 else 14
        if not stars:
            text(draw, (x + 20, y + 88), "本层无安星", 18, MUTED)
        for index, name in enumerate(stars):
            sy = y + 80 + index * step
            row = mapped.get(name)
            number = row["number"] if row else None
            prefix = number if row else "—"
            text(draw, (x + 20, sy + 2), prefix, size - 3, LAVENDER if life else MUTED)
            text(draw, (x + 60, sy), name, size, INK if name in MAJOR_ORDER else MUTED)
            hua = next((h for h, n in trad["four_hua"].items() if n == name), None)
            if hua:
                text(
                    draw,
                    (x + CELL - 22, sy + 2),
                    "化" + hua,
                    max(12, size - 5),
                    LAVENDER,
                    anchor="rt",
                )
            labels.append(
                {
                    "key": row["key"] if row else f"symbol:{name}",
                    "kind": "shared_star" if row else "symbolic",
                    "name": name,
                    "number": number,
                    "branch": branch,
                    "cell_box": cell,
                    "box": [x + 17, sy - 1, x + CELL - 17, sy + size + 4],
                }
            )
    cx, cy = ox + CELL * 2, oy + CELL * 2
    lunar, bureau = trad["lunar"], trad["bureau"]
    text(draw, (cx, cy - 137), "TRADITIONAL CHART", 16, MUTED, anchor="mt")
    text(
        draw,
        (cx, cy - 88),
        f"{bureau['element']}{'一二三四五六'[bureau['number'] - 1]}局",
        49,
        anchor="mt",
        strong=True,
    )
    text(
        draw,
        (cx, cy - 15),
        f"{trad['year_stem_branch']}年 · {'闰' if lunar['leap'] else ''}"
        f"{lunar['month']}月{lunar['day']}日 · {trad['hour_branch']}时",
        23,
        MUTED,
        anchor="mt",
    )
    text(
        draw,
        (cx, cy + 33),
        f"命宫 {trad['life_branch']}   /   身宫 {trad['body_branch']}",
        26,
        LAVENDER,
        anchor="mt",
    )
    rule(draw, (cx - 145, cy + 90), (cx + 145, cy + 90))
    text(draw, (cx, cy + 118), "星名在本宫 · 编号与天球对应", 20, MUTED, anchor="mt")
    text(draw, (cx, cy + 157), "— 暂未采用单体映射", 18, MUTED, anchor="mt")
    return labels


def region_labels(regions, traditional, names):
    """关联宫名只在完整文本框都属于本支的空白区域内落位。"""
    occupied = [r["box"] for r in names]
    occupied += [
        [r["point_px"][0] - 14, r["point_px"][1] - 14, r["point_px"][0] + 14, r["point_px"][1] + 14]
        for r in names
    ]
    occupied += [[548, 578, 652, 630], [600, 336, 720, 365]]
    result, omitted = [], []
    for index, branch in enumerate(BRANCHES):
        title = branch + " · " + traditional["palace_names"][branch]
        width, height = math.ceil(measure(title, 18)) + 12, 30
        candidates = []
        for y in range(130, 1070, 22):
            for x in range(130, 1070, 22):
                if regions[y, x] != index:
                    continue
                bounds = [x - width // 2, y - height // 2, x + (width + 1) // 2, y + height // 2]
                x1, y1, x2, y2 = bounds
                if not free_box(bounds, occupied) or not np.all(
                    regions[y1 : y2 + 1, x1 : x2 + 1] == index
                ):
                    continue
                # 偏向宽阔的片区；不放大真实区域来容纳标签。
                clearance = 0
                for distance in (15, 30, 50, 75, 100):
                    if all(
                        0 <= y + dy < PANEL
                        and 0 <= x + dx < PANEL
                        and regions[y + dy, x + dx] == index
                        for dx, dy in ((distance, 0), (-distance, 0), (0, distance), (0, -distance))
                    ):
                        clearance = distance
                    else:
                        break
                near = min(math.hypot(x - r["point_px"][0], y - r["point_px"][1]) for r in names)
                candidates.append((clearance * 2 + min(near, 130), bounds))
        if not candidates:
            omitted.append(branch)
            continue
        _, bounds = max(candidates, key=lambda p: p[0])
        occupied.append(bounds)
        result.append({"branch": branch, "title": title, "box": bounds})
    return result, omitted


def sky_panel(rows, traditional):
    regions = region_map(rows, PANEL, CENTER, RADIUS)
    edge = boundary_mask(regions)
    yy, xx = np.ogrid[:PANEL, :PANEL]
    distance = np.hypot(xx - CENTER, yy - CENTER)
    pixels = np.empty((PANEL, PANEL, 3), dtype=np.uint8)
    pixels[:] = (10, 10, 11)
    pixels[regions >= 0] = (17, 17, 20)
    pixels[(regions >= 0) & (distance < RADIUS / 2)] = (24, 24, 28)
    life_index = BRANCHES.index(traditional["life_branch"])
    pixels[regions == life_index] = (31, 33, 57)
    pixels[(regions == life_index) & (distance < RADIUS / 2)] = (39, 42, 69)
    pixels[edge] = (76, 77, 92)
    pixels[regions == -2] = (76, 77, 92)
    image = Image.fromarray(pixels).resize((PANEL * SCALE, PANEL * SCALE), Image.Resampling.BICUBIC)
    draw = ImageDraw.Draw(image, "RGBA")

    def circle(radius, color):
        draw.ellipse(
            tuple(
                v * SCALE
                for v in (CENTER - radius, CENTER - radius, CENTER + radius, CENTER + radius)
            ),
            outline=color,
            width=SCALE,
        )

    for fraction in (1 / 6, 1 / 3, 2 / 3, 5 / 6):
        circle(RADIUS * fraction, (255, 255, 255, 18))
    circle(RADIUS, (210, 212, 230, 105))
    circle(RADIUS / 2, (218, 220, 241, 175))
    for degree in range(0, 360, 10):
        angle = math.radians(degree)
        length = 10 if degree % 30 == 0 else 5
        rule(
            draw,
            (CENTER - (RADIUS + 7) * math.sin(angle), CENTER - (RADIUS + 7) * math.cos(angle)),
            (
                CENTER - (RADIUS + 7 + length) * math.sin(angle),
                CENTER - (RADIUS + 7 + length) * math.cos(angle),
            ),
            (255, 255, 255, 85),
        )
    for xy, title in (
        ((600, 43), "北 N"),
        ((42, 600), "东 E"),
        ((1156, 600), "西 W"),
        ((600, 1157), "南 S"),
    ):
        text(draw, xy, title, 20, MUTED, anchor="mm")
    text(draw, (600, 612), "天顶", 16, MUTED, anchor="mm")
    text(draw, (CENTER + 8, CENTER - RADIUS / 2 + 12), "0° 地平线", 15, MUTED)
    names = name_layout(
        [{**row, "target": row["target"] + " · " + row["traditional_branch"]} for row in rows]
    )
    for label, row in zip(names, rows):
        label["secondary"] = (
            row["target"]
            + (" *" if row["mapping"]["convention"] else "")
            + " · "
            + row["traditional_branch"]
        )
    zones, omitted = region_labels(regions, traditional, names)
    for label in names:
        label["leader_visible"] = label["leader_visible"] and not any(
            segment_hits_box(*label["leader_line"], z["box"]) for z in zones
        )
        if label["leader_visible"]:
            rule(draw, *label["leader_line"], color=(200, 202, 223, 130))
    for label in zones:
        x1, y1, x2, y2 = label["box"]
        text(
            draw,
            ((x1 + x2) / 2, y1 + 4),
            label["title"],
            18,
            LAVENDER if label["branch"] == traditional["life_branch"] else MUTED,
            anchor="mt",
        )
    by_key = {r["key"]: r for r in rows}
    for label in names:
        row = by_key[label["key"]]
        x, y = label["point_px"]
        size = max(2.5, visual_style(row["magnitude"])[0])
        color = LAVENDER if row["traditional_branch"] == traditional["life_branch"] else INK
        bounds = tuple(v * SCALE for v in (x - size, y - size, x + size, y + size))
        draw.ellipse(
            bounds, fill=color if row["altitude_deg"] >= 0 else BG, outline=color, width=SCALE
        )
        if row["name"] == "太阳":
            rule(draw, (x - 9, y), (x + 9, y), color)
            rule(draw, (x, y - 9), (x, y + 9), color)
        x1, y1, x2, y2 = label["box"]
        # 星名底板只服务于可读性，真实点与边界数据保持原位。
        box(draw, [x1, y1, x2, y2], fill=(10, 10, 11, 242), outline=None, radius=4)
        text(draw, (x1 + 5, y1 + 2), label["primary"], 22, color, strong=True)
        text(draw, (x1 + 5, y1 + 30), label["secondary"], 16, MUTED)
    return (
        image,
        names,
        zones,
        {
            "profile": ASSOCIATION_PROFILE,
            "formula": FORMULA,
            "meaning": LIMITATION,
            "highlight_branch": traditional["life_branch"],
            "label_omitted_branches": omitted,
            "branches_without_seed": [
                b for b in BRANCHES if not any(r["traditional_branch"] == b for r in rows)
            ],
            "sample_size": PANEL,
            "edge_pixels": int(edge.sum()),
        },
    )


def render_ziwei_atlas(data, comparison):
    rows = named_rows(comparison)
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    draw = ImageDraw.Draw(image, "RGBA")
    text(draw, (56, 30), "STAR ORACLE  /  ZIWEI", 16, LAVENDER)
    text(draw, (52, 65), "紫微星图", 60, strong=True)
    text(draw, (355, 92), "天球与命盘", 26, MUTED)
    moment = datetime.fromisoformat(data["epoch_local"])
    site = data["site"]
    text(draw, (WIDTH - 56, 36), f"{moment:%Y.%m.%d   %H:%M:%S}", 35, anchor="rt")
    _fit(
        draw,
        (WIDTH - 56, 88),
        f"{site['label']}  ·  {data['timezone']}  ·  {moment:%z}",
        21,
        1250,
        MUTED,
        anchor="rt",
    )
    _fit(
        draw,
        (56, 148),
        f"纬度 {site['latitude']:.5f}°  /  经度 {site['longitude']:.5f}°"
        f"    ·    {data['time_note']}",
        18,
        WIDTH - 112,
        MUTED,
    )
    rule(draw, (56, 186), (WIDTH - 56, 186))
    text(draw, (56, 211), "01  真实天球", 26, strong=True)
    text(draw, (420, 217), "北上东左 · 站心全天方向", 18, MUTED)
    text(draw, (1324, 211), "02  传统十二宫", 26, strong=True)
    text(draw, (WIDTH - 112, 217), "同名 · 同编号", 18, MUTED, anchor="rt")
    disk, names, zones, association = sky_panel(rows, comparison["traditional"])
    image.paste(disk, tuple(v * SCALE for v in SKY_ORIGIN))
    draw = ImageDraw.Draw(image, "RGBA")
    # 圆盘顶端在标题下方；边缘的透明背景不擦除栏目文字。
    text(draw, (56, 211), "01  真实天球", 26, strong=True)
    text(draw, (420, 217), "北上东左 · 站心全天方向", 18, MUTED)
    traditional = palace_grid(draw, comparison, rows)
    _offset_layout(names, SKY_ORIGIN)
    _offset_layout(zones, SKY_ORIGIN)
    text(draw, (1324, 1304), "淡紫区域：命宫关联片区", 22, LAVENDER)
    text(draw, (1324, 1343), "依据：球面最近星 + 传统落宫；分区为表达模型。", 18, MUTED)
    rule(draw, (56, 1401), (WIDTH - 56, 1401))
    text(draw, (56, 1423), "03  天体索引", 25, strong=True)
    text(
        draw,
        (WIDTH - 56, 1429),
        "实心：地平线上方   /   空心：地平线下方   /   * 展示约定",
        18,
        MUTED,
        anchor="rt",
    )
    links = []
    for index, row in enumerate(rows):
        col, line = index % 4, index // 4
        x, y = 56 + col * 596, 1480 + line * 42
        text(draw, (x, y), row["number"], 17, LAVENDER)
        text(draw, (x + 37, y - 2), row["name"], 21, strong=True)
        text(
            draw,
            (x + 113, y + 1),
            row["traditional_branch"] + "·" + row["traditional_palace"],
            18,
            MUTED,
        )
        text(
            draw,
            (x + 253, y + 2),
            f"高度 {row['altitude_deg']:+.1f}°  /  方位 {row['azimuth_deg']:.1f}°",
            16,
            MUTED,
        )
        links.append(
            {
                "key": row["key"],
                "number": row["number"],
                "branch": row["traditional_branch"],
                "box": [x - 2, y - 4, x + 581, y + 29],
            }
        )
    rule(draw, (56, 1719), (WIDTH - 56, 1719))
    text(draw, (56, 1742), "实体日月 02  ·  北斗历史别名 07  ·  展示约定 08", 18, MUTED)
    text(draw, (WIDTH - 56, 1742), "JPL DE440s  /  ESA HIPPARCOS", 17, MUTED, anchor="rt")
    text(
        draw,
        (56, 1777),
        "星点为真实位置；区域由传统标签生成，可有多片或缺席。地平线上方不代表肉眼可见。",
        16,
        MUTED,
    )
    output = io.BytesIO()
    image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue(), {
        "traditional": traditional,
        "real_names": names,
        "region_names": zones,
        "links": links,
        "association": association,
    }


__all__ = ["PROFILE", "WIDTH", "HEIGHT", "SKY_ORIGIN", "render_ziwei_atlas", "INTER", "CJK"]
