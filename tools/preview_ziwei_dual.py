"""传统静态命盘与真实星盘并排的 Witchcore 本地预览。"""

import argparse
import asyncio
import copy
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from local_core.engine import PlanetEngine
from local_core.image_renderer import SCALE
from local_core.resources import DATA_DIR, prepare_all
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import MAJOR_ORDER, compute_ziwei
from local_core.ziwei_label_layout import OBJECT_ORDER, object_number
from local_core.ziwei_palace_display import prepare_display_layer
from local_core.ziwei_single_renderer import single_panel
from local_core.ziwei_theme import (
    FONT,
    GOLD,
    HERB,
    SECONDARY,
    background,
    card,
    moon_ornament,
    rune_title,
    text,
)
from tools.compare_ziwei_rules import SQUARE
from tools.ziwei_rules_research import compare_sky

PROFILE = "witchcore-traditional-real-dual-v1"
WIDTH, HEIGHT = 2400, 1880
REAL_ORIGIN = (1200, 202)
GRID_ORIGIN, CELL = (66, 266), 260
SAME = "#9fbdad"


def draw_traditional(image, comparison):
    draw = ImageDraw.Draw(image, "RGBA")
    traditional = comparison["traditional"]
    shared = {r["name"]: r for r in comparison["rows"]}
    layout = []
    for branch, (col, row) in SQUARE.items():
        x, y = GRID_ORIGIN[0] + col * CELL, GRID_ORIGIN[1] + row * CELL
        box = [x, y, x + CELL, y + CELL]
        border = (
            GOLD
            if branch == traditional["life_branch"]
            else (HERB if branch == traditional["body_branch"] else (201, 167, 78, 90))
        )
        draw.rectangle(
            tuple(v * SCALE for v in box), fill=(13, 11, 20, 230), outline=border, width=SCALE
        )
        title = (
            f"{traditional['palace_names'][branch]} · {traditional['palace_stems'][branch]}{branch}"
        )
        text(draw, (x + 14, y + 14), title, 24, GOLD)
        if branch == traditional["body_branch"]:
            text(draw, (x + CELL - 14, y + 18), "身", 18, SAME, anchor="rt")
        layout.append(
            {
                "key": f"palace:{branch}",
                "kind": "palace",
                "branch": branch,
                "label": title,
                "box": [x + 12, y + 10, x + CELL - 12, y + 47],
                "cell_box": box,
            }
        )
        stars = [
            (name, pos) for name, pos in traditional["positions"].items() if pos["branch"] == branch
        ]
        stars.sort(key=lambda item: OBJECT_ORDER.index(item[0]) if item[0] in shared else 100)
        step = min(32, (CELL - 76) / max(1, len(stars)))
        size = 22 if step >= 30 else 18 if step >= 24 else 14
        for index, (name, _) in enumerate(stars):
            sy = y + 59 + index * step
            number = object_number({"name": name}) if name in shared else None
            label = f"{number}  {name}" if number else f"[符] {name}"
            color = GOLD if name in MAJOR_ORDER else SECONDARY
            text(draw, (x + 14, sy), label, size, color)
            hua = [key for key, value in traditional["four_hua"].items() if value == name]
            if hua:
                text(draw, (x + 162, sy + 5), "化" + hua[0], 13, SECONDARY)
            if number:
                status = "同" if shared[name]["same_branch"] else "异"
                text(
                    draw,
                    (x + CELL - 22, sy + 3),
                    status,
                    16,
                    SAME if status == "同" else SECONDARY,
                    anchor="rt",
                )
            layout.append(
                {
                    "key": shared[name]["key"] if number else f"symbol:{name}",
                    "name": name,
                    "label": label,
                    "number": number,
                    "kind": "shared_star" if number else "symbolic",
                    "branch": branch,
                    "cell_box": box,
                    "box": [x + 12, sy - 2, x + CELL - 12, sy + size + 4],
                    "same_branch": shared[name]["same_branch"] if number else None,
                }
            )
    bureau = traditional["bureau"]
    cx = GRID_ORIGIN[0] + CELL * 2
    lunar = traditional["lunar"]
    center_rows = [
        (f"{bureau['element']}{bureau['number']}局", 40, GOLD),
        (
            f"农历 {traditional['year_stem_branch']}年 {'闰' if lunar['leap'] else ''}"
            f"{lunar['month']}月{lunar['day']}日",
            24,
            SECONDARY,
        ),
        (
            f"{traditional['hour_branch']}时 · {bureau['stem_branch']} · {bureau['nayin']}",
            23,
            SECONDARY,
        ),
        (f"命宫 {traditional['life_branch']} · 身宫 {traditional['body_branch']}", 27, GOLD),
        (f"紫微 {traditional['ziwei_branch']} · 天府 {traditional['tianfu_branch']}", 25, GOLD),
        ("25 个静态星曜 · 17 个共有编号", 20, SECONDARY),
        ("文昌、右弼及六煞标 [符]", 19, SECONDARY),
        ("静态安星核心，不含运限", 18, SECONDARY),
    ]
    for index, (value, size, color) in enumerate(center_rows):
        text(draw, (cx, 603 + index * 47), value, size, color, anchor="mt")
    return layout


def render_dual(data, comparison):
    image = background(WIDTH, HEIGHT, total_height=HEIGHT, scale=SCALE)
    card(image, (36, 1377, WIDTH - 36, 1694))
    card(image, (36, 1711, WIDTH - 36, HEIGHT - 30))
    rune_title(image, (44, 24), "紫微命盘 / 真实星盘 · 同时地对照", 40)
    draw = ImageDraw.Draw(image, "RGBA")
    moon_ornament(draw, anchor_x=2190)
    moment = datetime.fromisoformat(data["epoch_local"])
    site = data["site"]
    text(
        draw,
        (44, 82),
        f"{site['label']} · {moment:%Y-%m-%d %H:%M:%S %z} · {data['timezone']}",
        23,
        GOLD,
    )
    text(
        draw,
        (44, 120),
        f"纬度 {site['latitude']:.5f}° / 经度 {site['longitude']:.5f}° · 共有编号 01–17 · 本地预览",
        18,
        SECONDARY,
    )
    traditional = draw_traditional(image, comparison)
    layer = prepare_display_layer(copy.deepcopy(data["palace_layer"]))
    # 两侧采用同一传统历法版本命名事项宫，真实方向和研究宫界保持不变。
    common = comparison["traditional"]
    for sector in layer["sectors"]:
        sector["name"] = common["palace_names"][sector["branch"]]
        sector["body"] = sector["branch"] == common["body_branch"]
    disk, local_layout = single_panel(data["single_chart"]["objects"], layer)
    rows_by_key = {r["key"]: r for r in comparison["rows"]}
    disk_draw = ImageDraw.Draw(disk)
    real = []
    for label in local_layout:
        label = copy.deepcopy(label)
        if label["kind"] == "point_number":
            row = rows_by_key[label["key"]]
            x1, y1, x2, y2 = label["box"]
            text(
                disk_draw,
                ((x1 + x2) / 2, (y1 + y2) / 2),
                label["number"],
                14,
                SAME if row["same_branch"] else SECONDARY,
                anchor="mm",
                stroke=1,
            )
            label["same_branch"] = row["same_branch"]
            label["point_px"] = [
                REAL_ORIGIN[0] + 580 + label["point_xy"][0] * 492,
                REAL_ORIGIN[1] + 580 + label["point_xy"][1] * 492,
            ]
            label["leader_line"] = [
                [x + REAL_ORIGIN[0], y + REAL_ORIGIN[1]] for x, y in label["leader_line"]
            ]
        label["box"] = [label["box"][i] + REAL_ORIGIN[i % 2] for i in range(4)]
        real.append(label)
    image.paste(disk, tuple(v * SCALE for v in REAL_ORIGIN))
    draw = ImageDraw.Draw(image)
    text(draw, (66, 179), "传统紫微命盘 · 地支固定格", 28, GOLD)
    text(draw, (66, 222), "《全书》静态安星核心 · 宫内列星名与共有编号", 17, SECONDARY)
    text(draw, (1242, 179), "真实星盘 · 北天极投影", 28, GOLD)
    text(draw, (1242, 222), "星点保持真实坐标 · 紫色虚线是地平线 · 宫区为研究分区", 16, SECONDARY)
    changed = sum(not row["same_branch"] for row in comparison["rows"])
    text(draw, (56, 1393), "编号对照 · 传统宫 / 真实研究宫", 25, GOLD)
    text(
        draw,
        (WIDTH - 56, 1399),
        f"地支归属：{changed} 异 / {17 - changed} 同 · 同格为标签比较",
        18,
        SECONDARY,
        anchor="rt",
    )
    differences = []
    for index, row in enumerate(
        sorted(comparison["rows"], key=lambda r: OBJECT_ORDER.index(r["name"]))
    ):
        col, line = index % 4, index // 4
        x, y = 54 + col * 579, 1444 + line * 47
        number = object_number(row)
        text(draw, (x + 10, y), number + " " + row["name"], 21, GOLD if row["major"] else SECONDARY)
        owners = (
            f"{row['traditional_branch']}·{row['traditional_palace']} / "
            f"{row['real_research_branch']}·{row['real_research_palace']}"
        )
        text(draw, (x + 162, y + 3), owners, 19, SECONDARY)
        text(
            draw,
            (x + 544, y + 3),
            "同" if row["same_branch"] else "异",
            18,
            SAME if row["same_branch"] else SECONDARY,
        )
        differences.append(
            {
                "key": row["key"],
                "number": number,
                "traditional_branch": row["traditional_branch"],
                "real_research_branch": row["real_research_branch"],
                "same_branch": row["same_branch"],
                "box": [x + 8, y - 2, x + 568, y + 30],
            }
        )
    footer = [
        "同 / 异比较地支归属；真实侧的宫界为古界今星锚定研究层，尚非已认证古宫界。",
        "01 紫微采用现代北极星展示约定；南斗与左辅保留映射约定。"
        "文昌、右弼和六煞没有本次采用的单体位置。",
        "日月与恒星方向来自 NASA JPL DE440s / ESA Hipparcos；"
        "明暗按真实高度划分，不等同于庙旺或肉眼可见性。",
        "两侧使用同一当地民用日期和时辰，23点换日；研究闰月版本见 JSON。"
        "只做本地预览，未接入正式指令。",
    ]
    for index, value in enumerate(footer):
        text(draw, (54, 1730 + index * 31), value, 16, SECONDARY)
    stream = io.BytesIO()
    image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(stream, format="PNG")
    return stream.getvalue(), {"traditional": traditional, "real": real, "differences": differences}


async def preview(args):
    await prepare_all(DATA_DIR)
    core = PlanetEngine(DATA_DIR)
    try:
        sky = SkyChartEngine(core)
        data = compute_ziwei(sky, args.input)
        comparison = compare_sky(data, args.leap_policy)
        png, layout = render_dual(data, comparison)
        source_paths = [
            Path(__file__),
            Path(__file__).with_name("ziwei_rules_research.py"),
            Path(__file__).with_name("compare_ziwei_rules.py"),
        ]
        source_paths += [
            Path(__file__).parents[1] / "local_core" / name
            for name in (
                "ziwei_single_renderer.py",
                "ziwei_palace_display.py",
                "ziwei_label_layout.py",
                "ziwei_theme.py",
            )
        ]
        payload = {
            "profile": PROFILE,
            "request": args.input,
            "data": data,
            "comparison": comparison,
            "label_layout": layout,
            "real_panel_origin": list(REAL_ORIGIN),
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "font_sha256": hashlib.sha256(FONT.read_bytes()).hexdigest(),
            "code_sha256": {
                str(p.relative_to(Path(__file__).parents[1])): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in source_paths
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
                    "shared_numbers": 17,
                    "different": 17 - len(comparison["matching_names"]),
                    "same": comparison["matching_names"],
                },
                ensure_ascii=False,
            )
        )
    finally:
        core.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/星图 北京 20261012200000")
    parser.add_argument(
        "--leap-policy", choices=["quanshu_next", "preview_split"], default="quanshu_next"
    )
    parser.add_argument(
        "--output", type=Path, default=DATA_DIR / "ziwei-validation/dual/beijing.png"
    )
    asyncio.run(preview(parser.parse_args()))


if __name__ == "__main__":
    main()
