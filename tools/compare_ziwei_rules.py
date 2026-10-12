"""仅本地研究：传统安星核心与同一时刻真实天体逐项对照。"""

import argparse
import asyncio
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from local_core.engine import PlanetEngine
from local_core.image_renderer import SCALE
from local_core.resources import DATA_DIR, prepare_all
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import MAJOR_ORDER, compute_ziwei
from local_core.ziwei_theme import GOLD, SECONDARY, background, card, rune_title, text
from tools.ziwei_rules_research import SOURCE, compare_sky

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


def render_comparison(data, comparison, planets):
    image = background(2160, 1510, scale=SCALE)
    for box in (
        (28, 169, 1490, 945),
        (28, 967, 1490, 1310),
        (1512, 169, 2132, 336),
        (1512, 956, 2132, 1310),
        (28, 1342, 2132, 1485),
    ):
        card(image, box)
    rune_title(image, (38, 20), "紫微斗数安星 · 真实天体对照", 40)
    draw = ImageDraw.Draw(image, "RGBA")
    text(
        draw, (38, 76), f"{data['site']['label']} · {data['epoch_local']} · 本地研究样例", 21, GOLD
    )
    text(
        draw, (38, 111), "传统地支宫位与真实研究天区分列；恒星别名映射保留假设性质。", 18, SECONDARY
    )
    text(draw, (48, 180), "相同时间参数 · 17 个已采用实体映射的星名", 23, GOLD)
    for x, label in (
        (48, "星名"),
        (180, "本图采用的真实目标"),
        (565, "传统安星落宫"),
        (830, "真实研究天区"),
        (1085, "高度°"),
        (1210, "方位°"),
        (1340, "地支同格"),
    ):
        text(draw, (x, 226), label, 17, SECONDARY)
    for index, row in enumerate(sorted(comparison["rows"], key=lambda r: ORDER.index(r["name"]))):
        y = 264 + index * 38
        color = GOLD if row["major"] else SECONDARY
        text(draw, (48, y), row["name"], 21, color)
        # 图中转写拜耳名，避免随附字体中未收录的希腊字母；JSON 保留原文。
        greek = {
            "α": "alpha",
            "β": "beta",
            "γ": "gamma",
            "δ": "delta",
            "ε": "epsilon",
            "ζ": "zeta",
            "η": "eta",
            "λ": "lambda",
            "μ": "mu",
            "σ": "sigma",
            "τ": "tau",
            "φ": "phi",
        }
        target = row["real_target"].translate(str.maketrans(greek)) + (
            f" · HIP {row['hip']}" if row["hip"] else f" · NAIF {row['naif_id']}"
        )
        text(draw, (180, y + 3), target, 16, SECONDARY)
        text(draw, (565, y), f"{row['traditional_branch']} · {row['traditional_palace']}", 20, GOLD)
        text(
            draw,
            (830, y),
            f"{row['real_research_branch']} · {row['real_research_palace']}",
            20,
            SECONDARY,
        )
        text(draw, (1085, y + 2), f"{row['altitude_deg']:+.1f}", 18, SECONDARY)
        text(draw, (1210, y + 2), f"{row['azimuth_deg']:.1f}", 18, SECONDARY)
        text(
            draw,
            (1340, y + 2),
            "同格" if row["same_branch"] else "不同",
            18,
            "#9fbdad" if row["same_branch"] else SECONDARY,
        )
    traditional = comparison["traditional"]
    bureau = traditional["bureau"]
    text(
        draw,
        (1534, 186),
        f"{bureau['element']}{bureau['number']}局 · 农历生日 {traditional['lunar']['day']}",
        27,
        GOLD,
    )
    text(
        draw,
        (1534, 229),
        f"{traditional['year_stem_branch']}年 · {bureau['stem_branch']}命宫 · {bureau['nayin']}",
        21,
        SECONDARY,
    )
    text(
        draw,
        (1534, 268),
        f"紫微 {traditional['ziwei_branch']} · 天府 {traditional['tianfu_branch']}",
        23,
        GOLD,
    )
    hua = " / ".join(name + "化" + key for key, name in traditional["four_hua"].items())
    text(draw, (1534, 307), hua, 16, SECONDARY)
    text(draw, (1534, 355), "传统静态安星盘 · 地支固定格", 23, GOLD)
    for branch, (col, row) in SQUARE.items():
        x, y = 1544 + col * 142, 393 + row * 132
        draw.rectangle(
            tuple(v * SCALE for v in (x, y, x + 142, y + 132)),
            fill=(13, 11, 20, 200),
            outline=(201, 167, 78, 100),
            width=SCALE,
        )
        palace = traditional["palace_names"][branch]
        text(draw, (x + 8, y + 8), branch + " · " + palace, 17, GOLD)
        placed = [name for name, pos in traditional["positions"].items() if pos["branch"] == branch]
        cols = 2 if len(placed) > 4 else 1
        rows = (len(placed) + cols - 1) // cols
        step = min(16, 82 / max(1, rows))
        for i, name in enumerate(placed):
            text(
                draw,
                (x + 8 + i % cols * 63, y + 35 + i // cols * step),
                name,
                14 if rows <= 5 else 12,
                GOLD if name in MAJOR_ORDER else SECONDARY,
            )
    text(draw, (1699, 552), "传统符号落宫", 21, GOLD)
    text(
        draw,
        (1699, 590),
        f"命宫 {traditional['life_branch']} / 身宫 {traditional['body_branch']}",
        18,
        SECONDARY,
    )
    text(draw, (1699, 627), "14 主星 + 5 辅星 + 6 煞", 17, SECONDARY)
    text(draw, (1699, 664), "静态盘，不含运限", 17, SECONDARY)
    main_matches = sum(r["major"] and r["same_branch"] for r in comparison["rows"])
    text(draw, (1534, 974), "本样例的对照结果", 24, GOLD)
    text(draw, (1534, 1017), f"十四主星：{main_matches} 个地支同格", 23, GOLD)
    matches = "、".join(comparison["matching_names"]) or "无"
    text(draw, (1534, 1060), f"17 个映射天体：同格为 {matches}", 21, GOLD)
    for i, value in enumerate(
        (
            "这个结果依赖当前星名映射与研究宫界。",
            "地支标签比较，不是实际角度差或正确率。",
            "不能据此认定传统安星是天文坐标算法。",
            "六煞仍为符号，不自动把斗数火星当 Mars。",
        )
    ):
        text(draw, (1534, 1120 + i * 36), value, 18, SECONDARY)
    text(draw, (48, 979), "另列七颗实体行星 · JPL 状态，不强配斗数星曜", 23, GOLD)
    for i, planet in enumerate(planets):
        y = 1020 + i * 37
        text(draw, (48, y), planet["name"], 20, GOLD)
        text(draw, (180, y + 2), f"NAIF {planet['naif_id']}", 17, SECONDARY)
        text(draw, (350, y + 2), f"高度 {planet['altitude_deg']:+.1f}°", 18, SECONDARY)
        text(draw, (575, y + 2), f"方位 {planet['azimuth_deg']:.1f}°", 18, SECONDARY)
        text(draw, (805, y + 2), planet["comparison_note"], 17, SECONDARY)
    for i, value in enumerate(
        (
            "传统核心：命身 → 命宫干支纳音 → 五行局与农历生日定紫微 → 紫微、天府两组安星。"
            "四化是星曜属性，庙旺不等于视星等。",
            "本图沿用地点民用日期转中国农历、23点换日；《全书》闰月取次月另列研究版本。录文异字、闰月、四化流派差异已记录。",
            "真实状态来自 JPL DE440s / ESA Hipparcos；紫微＝现代北极星、南斗及左辅为展示约定，"
            "研究宫界不是已认证古宫界。",
            "依据：《紫微斗数全书》卷二固定录文与 iztro 2.6.1 独立交叉核对；"
            "只做规则与坐标比较，不作预测能力验证。",
        )
    ):
        text(draw, (38, 1355 + i * 32), value, 15, SECONDARY)
    stream = io.BytesIO()
    image.resize((2160, 1510), Image.Resampling.LANCZOS).save(stream, format="PNG")
    return stream.getvalue()


async def compare(args):
    await prepare_all(DATA_DIR)
    core = PlanetEngine(DATA_DIR)
    try:
        sky = SkyChartEngine(core)
        data = compute_ziwei(sky, args.input)
        result = compare_sky(data, args.leap_policy)
        plain = sky.compute(data["epoch_utc"], data["site"], data["timezone"])
        planets = [dict(p) for scene in plain["hemispheres"].values() for p in scene["planets"]]
        for planet in planets:
            planet["comparison_note"] = "尚无本研究采用的斗数单体映射"
            if planet["key"] == "mars":
                planet["comparison_note"] = "Mars 不自动等于斗数的火星符号"
        png = render_comparison(data, result, planets)
        payload = {
            "request": args.input,
            "epoch_utc": data["epoch_utc"],
            "epoch_local": data["epoch_local"],
            "site": data["site"],
            "comparison": result,
            "real_planets_without_mapping": planets,
            "astronomy_provenance": data["provenance"],
            "book_source": SOURCE,
            "source_snapshots": json.loads(
                (DATA_DIR / "ziwei-validation/rule-sources/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            if (DATA_DIR / "ziwei-validation/rule-sources/manifest.json").exists()
            else None,
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "research_code_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), Path(__file__).with_name("ziwei_rules_research.py"))
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        args.output.with_suffix(".png").write_bytes(png)
        print(args.output.resolve())
        print(
            json.dumps(
                {
                    "bureau": result["traditional"]["bureau"],
                    "same_branch_names": result["matching_names"],
                    "real_planets": len(planets),
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
        "--output", type=Path, default=DATA_DIR / "ziwei-validation/rules-comparison/beijing.json"
    )
    asyncio.run(compare(parser.parse_args()))


if __name__ == "__main__":
    main()
