"""紫微星名的单盘明暗预览；煞星对应尚待用户确认。"""

import io
import math
from datetime import datetime

from PIL import Image, ImageDraw

from .image_renderer import SCALE, fitted_text, font, text, visual_style
from .ziwei_chart import MAJOR_ORDER

MAIN = "#ffe0a0"
AUX = "#81cfc8"


def single_panel(objects, sectors, symbols):
    image = Image.new("RGB", (1160 * SCALE, 1160 * SCALE), "#101b25")
    draw = ImageDraw.Draw(image, "RGBA")
    center, radius = 580, 492

    def point(xy):
        return ((center + xy[0] * radius) * SCALE, (center + xy[1] * radius) * SCALE)

    def circle(px, py, r, **kwargs):
        r *= SCALE
        draw.ellipse((px - r, py - r, px + r, py + r), **kwargs)

    circle(center * SCALE, center * SCALE, radius, fill="#171c28", outline="#655b78", width=SCALE)
    circle(
        center * SCALE, center * SCALE, radius / 2, fill="#17333f", outline="#7db7aa", width=SCALE
    )
    for fraction, label in (
        (1 / 6, "+60°"),
        (1 / 3, "+30°"),
        (1 / 2, "0° 地平线"),
        (2 / 3, "−30°"),
        (5 / 6, "−60°"),
    ):
        if fraction != 1 / 2:
            circle(
                center * SCALE,
                center * SCALE,
                radius * fraction,
                outline=(88, 115, 127, 100),
                width=SCALE,
            )
        text(draw, (center + 6, center - radius * fraction + 9), label, 14, "#839ca8")
    for az in range(0, 360, 30):
        angle = math.radians(az)
        draw.line(
            [point((0, 0)), point((math.sin(angle), -math.cos(angle)))],
            fill=(135, 164, 176, 35),
            width=SCALE,
        )
    for sector in sectors:
        color = (188, 171, 122, 115) if sector["name"] == "命宫" else (121, 152, 159, 85)
        for curve in sector["curves"]:
            draw.line([point(xy) for xy in curve], fill=color, width=SCALE)
    for xy, value in (
        ((580, 54), "北"),
        ((54, 580), "东"),
        ((1106, 580), "西"),
        ((580, 1106), "南"),
    ):
        text(draw, xy, value, 22, "#a8cbbb", anchor="mm")
    text(draw, (580, 598), "天顶", 15, "#819aa5", anchor="mm")
    text(draw, (580, 1140), "外缘为天底极限 · 全天方向在同一盘内", 15, "#8f9eaa", anchor="mm")
    dots = []
    for obj in objects:
        px, py = point(obj["single_xy"])
        dots.append((px / SCALE - 10, py / SCALE - 10, px / SCALE + 10, py / SCALE + 10))
        bright = obj["display_state"] == "bright"
        color = MAIN if obj["major"] else AUX
        if obj["kind"] == "star":
            r, alpha = visual_style(obj["magnitude"])
            circle(px, py, r, fill=(226, 235, 247, round(alpha * (255 if bright else 115))))
        else:
            circle(px, py, 4, outline=color if bright else "#80796e", width=SCALE)
            if obj["kind"] == "sun":
                for angle in range(0, 360, 45):
                    angle = math.radians(angle)
                    draw.line(
                        [
                            (px + r * SCALE * math.cos(angle), py + r * SCALE * math.sin(angle))
                            for r in (9, 13)
                        ],
                        fill=color if bright else "#80796e",
                        width=SCALE,
                    )
        circle(
            px, py, 8 if obj["major"] else 5, outline=color if bright else "#857c6f", width=SCALE
        )
    reserved = [
        (552, 585, 609, 612),
        (557, 40, 603, 73),
        (557, 1086, 603, 1126),
        (39, 560, 69, 603),
        (1090, 560, 1122, 603),
    ]
    for fraction in (1 / 6, 1 / 3, 1 / 2, 2 / 3, 5 / 6):
        reserved.append((582, center - radius * fraction + 7, 679, center - radius * fraction + 32))
    layout = []
    for obj in sorted(objects, key=lambda o: (not o["major"], o["key"])):
        size = 25 if obj["major"] else 17
        value = obj["name"] + ("*" if obj["name"] == "紫微" else "")
        width = draw.textlength(value, font=font(size)) / SCALE
        px, py = (v / SCALE for v in point(obj["single_xy"]))
        chosen = None
        for distance in (18, 36, 55, 80, 112, 150, 195, 245, 300):
            for angle in (0, 180, 45, 315, 135, 225, 90, 270):
                angle = math.radians(angle)
                dx, dy = distance * math.cos(angle), distance * math.sin(angle)
                x = px + dx - (width if dx < -1 else width / 2 if abs(dx) < 1 else 0)
                y = py + dy - size / 2
                box = (x - 3, y - 3, x + width + 3, y + size + 7)
                if box[0] < 12 or box[2] > 1148 or box[1] < 80 or box[3] > 1080:
                    continue
                if all(
                    box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
                    for b in reserved + dots
                ):
                    chosen = (x, y, box)
                    break
            if chosen:
                break
        if chosen is None:
            raise ValueError(f"单盘标签无法避让：{obj['name']}")
        x, y, box = chosen
        bright = obj["display_state"] == "bright"
        color = (MAIN if obj["major"] else AUX) if bright else "#aaa29a"
        endpoint = (min(max(px, x), x + width), min(max(py, y), y + size))
        draw.line(
            [(px * SCALE, py * SCALE), tuple(v * SCALE for v in endpoint)],
            fill=(196, 191, 170, 180 if bright else 100),
            width=SCALE,
        )
        text(draw, (x, y), value, size, color, stroke=2)
        reserved.append(box)
        layout.append({"key": obj["key"], "label": value, "box": list(box)})
    draw_palace_labels(draw, objects, sectors, layout, reserved)
    draw_malefic_symbols(draw, objects, symbols, layout, reserved)
    return image, layout


def draw_palace_labels(draw, objects, sectors, layout, reserved):
    dots = [
        (
            580 + o["single_xy"][0] * 492 - 10,
            580 + o["single_xy"][1] * 492 - 10,
            580 + o["single_xy"][0] * 492 + 10,
            580 + o["single_xy"][1] * 492 + 10,
        )
        for o in objects
    ]
    for sector in sectors:
        value = f"{sector['name']}·{sector['branch']}"
        subtitle = sector["ci"] + (" / 身宫" if sector["body"] else "")
        width = (
            max(draw.textlength(value, font=font(18)), draw.textlength(subtitle, font=font(13)))
            / SCALE
        )
        px, py = (580 + v * 492 for v in sector["label_xy"])
        chosen = None
        for distance in (17, 40, 65, 95, 135, 180, 230, 290, 350):
            for angle in (0, 180, 45, 315, 135, 225, 90, 270):
                angle = math.radians(angle)
                dx, dy = distance * math.cos(angle), distance * math.sin(angle)
                x = px + dx - (width if dx < -1 else width / 2 if abs(dx) < 1 else 0)
                y = py + dy - 20
                box = (x - 3, y - 3, x + width + 3, y + 45)
                if box[0] < 12 or box[2] > 1148 or box[1] < 80 or box[3] > 1080:
                    continue
                if all(
                    box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
                    for b in reserved + dots
                ):
                    chosen = (x, y, box)
                    break
            if chosen:
                break
        if chosen is None:
            raise ValueError(f"宫名无法避让：{value}")
        x, y, box = chosen
        color = "#dfbf82" if sector["name"] == "命宫" else "#90adb7"
        endpoint = (min(max(px, x), x + width), min(max(py, y), y + 40))
        draw.line(
            [(px * SCALE, py * SCALE), tuple(v * SCALE for v in endpoint)],
            fill=(127, 161, 167, 90),
            width=SCALE,
        )
        text(draw, (x, y), value, 18, color, stroke=2)
        text(draw, (x, y + 25), subtitle, 13, "#718e9c", stroke=1)
        reserved.append(box)
        layout.append({"key": f"palace:{sector['branch']}", "label": value, "box": list(box)})


def draw_malefic_symbols(draw, objects, symbols, layout, reserved):
    dots = [
        (
            580 + o["single_xy"][0] * 492 - 10,
            580 + o["single_xy"][1] * 492 - 10,
            580 + o["single_xy"][0] * 492 + 10,
            580 + o["single_xy"][1] * 492 + 10,
        )
        for o in objects
    ]
    for symbol in symbols:
        marker = None
        for xy in symbol["layout_options"]:
            px, py = (580 + v * 492 for v in xy)
            box = (px - 9, py - 9, px + 9, py + 9)
            if all(
                box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
                for b in reserved + dots
            ):
                marker = (px, py, xy, box)
                break
        if marker is None:
            raise ValueError(f"煞星符号无法避让：{symbol['name']}")
        px, py, xy, box = marker
        reserved.append(box)
        draw.polygon(
            [
                (px * SCALE, (py - 6) * SCALE),
                ((px + 6) * SCALE, py * SCALE),
                (px * SCALE, (py + 6) * SCALE),
                ((px - 6) * SCALE, py * SCALE),
            ],
            fill="#de9d89",
        )
        value = symbol["name"] + "[符]"
        width = draw.textlength(value, font=font(18)) / SCALE
        chosen = None
        for distance in (16, 35, 60, 90, 130, 175, 230, 290):
            for angle in (0, 180, 45, 315, 135, 225, 90, 270):
                angle = math.radians(angle)
                dx, dy = distance * math.cos(angle), distance * math.sin(angle)
                x = px + dx - (width if dx < -1 else width / 2 if abs(dx) < 1 else 0)
                y = py + dy - 9
                box = (x - 3, y - 3, x + width + 3, y + 25)
                if box[0] < 12 or box[2] > 1148 or box[1] < 80 or box[3] > 1080:
                    continue
                if all(
                    box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
                    for b in reserved + dots
                ):
                    chosen = (x, y, box)
                    break
            if chosen:
                break
        if chosen is None:
            raise ValueError(f"煞星符号标签无法避让：{value}")
        x, y, box = chosen
        endpoint = (min(max(px, x), x + width), min(max(py, y), y + 18))
        draw.line(
            [(px * SCALE, py * SCALE), tuple(v * SCALE for v in endpoint)],
            fill=(222, 157, 137, 150),
            width=SCALE,
        )
        text(draw, (x, y), value, 18, "#de9d89", stroke=2)
        reserved.append(box)
        layout.append(
            {
                "key": symbol["key"],
                "label": value,
                "box": list(box),
                "marker_xy": xy,
                "marker_box": list(marker[3]),
                "kind": "symbolic",
            }
        )


def render_ziwei_png(data):
    image = Image.new("RGB", (1680 * SCALE, 1510 * SCALE), "#101b25")
    draw = ImageDraw.Draw(image)
    text(draw, (38, 20), "星图 · 紫微星名", 38, "#f2e6c9")
    text(draw, (1638, 43), "明暗 / 十二宫 / 视星等 · 本地测试", 19, "#b6c3c6", anchor="rt")
    moment = datetime.fromisoformat(data["epoch_local"])
    site = data["site"]
    fitted_text(
        draw,
        (38, 71),
        f"{site['label']} · {moment:%Y-%m-%d %H:%M:%S %z} · {data['timezone']}",
        21,
        "#bcd0d1",
        1580,
    )
    fitted_text(
        draw,
        (38, 103),
        f"纬度 {site['latitude']:.5f}° / 经度 {site['longitude']:.5f}° · {data['time_note']}",
        17,
        "#93adb3",
        1600,
    )
    objects = data["single_chart"]["objects"]
    layer = data["palace_layer"]
    assignment = layer["assignment"]
    if assignment["available"]:
        lunar = assignment["lunar"]
        value = (
            f"农历 {lunar['year']}年{'闰' if lunar['leap'] else ''}{lunar['month']}月"
            f"{lunar['day']}日 · {assignment['hour_branch']}时 · "
            f"命宫 {assignment['life_branch']} / 身宫 {assignment['body_branch']} · "
            "古界今星锚定研究层"
        )
    else:
        value = assignment["reason"] + "；仅显示星次研究界"
    fitted_text(draw, (38, 133), value, 16, "#a7b4b4", 1600)
    symbols = layer["symbolic_malefics"]
    disk, layout = single_panel(objects, layer["sectors"], symbols)
    image.paste(disk, (0, 176 * SCALE))
    text(draw, (1190, 171), "十四主星", 25, MAIN)
    text(draw, (1190, 211), "星名    V星等    明暗    高度      宫位", 16, "#97abb7")
    lookup = {obj["name"]: obj for obj in objects}
    for index, name in enumerate(MAJOR_ORDER):
        obj = lookup[name]
        bright = obj["display_state"] == "bright"
        y = 250 + index * 35
        text(draw, (1190, y), name, 20, MAIN if bright else "#aaa29a")
        estimated = "~" if obj["kind"] != "star" else ""
        text(draw, (1264, y + 1), f"{estimated}{obj['magnitude']:+.1f}", 16, "#b8c9d3")
        text(draw, (1357, y + 1), "明" if bright else "暗", 17, "#a6dfcc" if bright else "#9293ab")
        text(draw, (1403, y + 1), f"{obj['altitude_deg']:+.1f}°", 16, "#abbac4")
        text(draw, (1512, y + 1), obj["research_palace"], 17, "#90adb7")
    text(draw, (1190, 780), "辅星", 23, AUX)
    for index, name in enumerate(("禄存", "文曲", "左辅")):
        obj = lookup[name]
        text(
            draw,
            (1190, 819 + index * 32),
            f"{name} · {'明' if obj['display_state'] == 'bright' else '暗'} · "
            f"V {obj['magnitude']:+.2f} · {obj['research_palace']}",
            16,
            AUX,
        )
    text(draw, (1190, 925), "星等越小越亮；~ 为模型估算", 15, "#90a5b1")
    text(draw, (1190, 960), "六煞 · 安星符号", 23, "#deab9d")
    for index, symbol in enumerate(symbols):
        text(
            draw,
            (1190, 1005 + index * 34),
            f"{symbol['name']} · {symbol['branch']} · {symbol['palace']}",
            19,
            "#de9d89",
        )
    text(draw, (1190, 1230), "菱形 / [符]：无实体坐标和视星等", 15, "#929da8")
    text(
        draw,
        (38, 1355),
        "明：高度 ≥ 0°，在地平线以上；暗：高度 < 0°，被地球遮挡。"
        "本图明暗不等同于斗数庙旺落陷或实际肉眼可见性。",
        16,
        "#b9cbd0",
    )
    text(
        draw,
        (38, 1387),
        "* 紫微采用现代北极星展示约定；主星大字，辅星小字。恒星点按 V 星等，日月使用定位符号。",
        15,
        "#a9b9c1",
    )
    text(
        draw,
        (38, 1419),
        "天顶中心的全天等距方位投影 · 坐标 ESA Hipparcos / NASA JPL DE440s · "
        "地点 GeoNames CC BY 4.0",
        14,
        "#839ba7",
    )
    text(
        draw,
        (38, 1449),
        "宫界：晋书主表按当前候选距星锚定的研究示意；命宫等按当地民用时安宫，"
        "不是已认证古宫界。V星等未计大气、云层、食与天空背景。",
        14,
        "#a1a8af",
    )
    output = io.BytesIO()
    image.resize((1680, 1510), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue(), {"single": layout}
