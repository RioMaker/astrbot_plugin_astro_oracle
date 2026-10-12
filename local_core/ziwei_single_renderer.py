"""紫微星名的北天极星盘；宫区显示与真实明暗分开。"""

import io
import math
from datetime import datetime

from PIL import Image, ImageDraw

from .image_renderer import SCALE, fitted_text, font, text, visual_style
from .ziwei_chart import MAJOR_ORDER
from .ziwei_palace_display import (
    DISPLAY_PROFILE,
    box_inside_palace,
    horizon_curves,
    palace_background,
    palace_label_candidates,
    palace_region_map,
    prepare_display_layer,
)

MAIN = "#ffe0a0"
AUX = "#81cfc8"


def single_panel(objects, layer):
    sectors = layer["sectors"]
    region_map = palace_region_map(layer)
    image = palace_background(layer, region_map).resize(
        (1160 * SCALE, 1160 * SCALE), Image.Resampling.BILINEAR
    )
    draw = ImageDraw.Draw(image, "RGBA")
    center, radius = 580, 492

    def point(xy):
        return ((center + xy[0] * radius) * SCALE, (center + xy[1] * radius) * SCALE)

    def circle(px, py, r, **kwargs):
        r *= SCALE
        draw.ellipse((px - r, py - r, px + r, py + r), **kwargs)

    circle(center * SCALE, center * SCALE, radius, outline="#655b78", width=SCALE)
    circle(center * SCALE, center * SCALE, radius / 2, outline="#596c8c", width=SCALE)
    for fraction, label in (
        (1 / 6, "赤纬 +60°"),
        (1 / 3, "+30°"),
        (1 / 2, "0° 赤道"),
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
    for index, sector in enumerate(sectors):
        previous = sectors[(index - 1) % len(sectors)]
        if sector["name"] == "命宫" or previous["name"] == "命宫":
            color, width = (222, 189, 128, 190), 2 * SCALE
        elif sector["body"] or previous["body"]:
            color, width = (111, 189, 161, 185), 2 * SCALE
        else:
            color, width = (121, 152, 159, 105), SCALE
        for curve in sector["curves"]:
            draw.line([point(xy) for xy in curve], fill=color, width=width)
    for curve in horizon_curves(layer):
        draw.line([point(xy) for xy in curve], fill=(173, 192, 194, 195), width=2 * SCALE)
    for xy, value in (
        ((580, 54), "00h"),
        ((54, 580), "06h"),
        ((1106, 580), "18h"),
        ((580, 1106), "12h"),
    ):
        text(draw, xy, value, 22, "#a8cbbb", anchor="mm")
    text(draw, (580, 598), "北天极", 15, "#819aa5", anchor="mm")
    text(draw, (580, 1140), "外缘为南天极极限 · 方位环为日期真赤经", 15, "#8f9eaa", anchor="mm")
    dots = []
    for obj in objects:
        px, py = point(obj["display_xy"])
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
    draw_palace_labels(draw, objects, layer, region_map, layout, reserved)
    draw_malefic_symbols(draw, objects, layer, region_map, layout, reserved)
    for obj in sorted(objects, key=lambda o: (not o["major"], o["key"])):
        size = 25 if obj["major"] else 17
        value = obj["name"] + ("*" if obj["name"] == "紫微" else "")
        width = draw.textlength(value, font=font(size)) / SCALE
        px, py = (v / SCALE for v in point(obj["display_xy"]))
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
    return image, layout


def draw_palace_labels(draw, objects, layer, region_map, layout, reserved):
    dots = [
        (
            580 + o["display_xy"][0] * 492 - 10,
            580 + o["display_xy"][1] * 492 - 10,
            580 + o["display_xy"][0] * 492 + 10,
            580 + o["display_xy"][1] * 492 + 10,
        )
        for o in objects
    ]
    sectors = sorted(
        layer["sectors"],
        key=lambda sector: (sector["name"] != "命宫", not sector["body"], sector["start_ra_deg"]),
    )
    for sector in sectors:
        value = f"{sector['name']} {sector['branch']}"
        tag = "命身" if sector["body"] and sector["name"] == "命宫" else "身宫"
        subtitle = sector["ci"] + (f" · {tag}" if sector["body"] else "")
        size = 21 if sector["name"] == "命宫" else 19
        width = (
            max(draw.textlength(value, font=font(size)), draw.textlength(subtitle, font=font(13)))
            / SCALE
        ) + 20
        width = max(108, width)
        chosen = None
        for _, box, xy in palace_label_candidates(sector, width, 58):
            if not all(
                box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
                for b in reserved + dots
            ):
                continue
            if box_inside_palace(box, sector["branch"], region_map):
                chosen = (box, xy)
                break
        if chosen is None:
            raise ValueError(f"宫名没有可容纳完整文字框的本宫位置：{value}")
        box, xy = chosen
        x, y = box[:2]
        if sector["name"] == "命宫":
            border, color = "#c6a46b", "#f4d194"
        elif sector["body"]:
            border, color = "#6fac97", "#b3decf"
        else:
            border, color = "#456473", "#b8cbd5"
        draw.rounded_rectangle(
            tuple(v * SCALE for v in box),
            radius=7 * SCALE,
            fill=(12, 24, 32, 235),
            outline=border,
            width=SCALE,
        )
        text(draw, (x + 10, y + 8), value, size, color)
        text(draw, (x + 10, y + 34), subtitle, 13, "#8fbaab" if sector["body"] else "#7895a4")
        reserved.append(box)
        layout.append(
            {
                "key": f"palace:{sector['branch']}",
                "label": value,
                "box": list(box),
                "branch": sector["branch"],
                "kind": "palace",
                "placement": "inside_region",
                "label_center_xy": xy,
                "display_profile": DISPLAY_PROFILE,
            }
        )


def draw_malefic_symbols(draw, objects, layer, region_map, layout, reserved):
    dots = [
        (
            580 + o["display_xy"][0] * 492 - 10,
            580 + o["display_xy"][1] * 492 - 10,
            580 + o["display_xy"][0] * 492 + 10,
            580 + o["display_xy"][1] * 492 + 10,
        )
        for o in objects
    ]
    for symbol in layer["symbolic_malefics"]:
        value = symbol["name"] + "[符]"
        width = draw.textlength(value, font=font(18)) / SCALE
        sector = next(s for s in layer["sectors"] if s["branch"] == symbol["branch"])
        chosen = None
        for _, box, _ in palace_label_candidates(sector, width + 32, 32, preferred_dec=0):
            if box_inside_palace(box, symbol["branch"], region_map) and all(
                box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]
                for b in reserved + dots
            ):
                chosen = box
                break
        if chosen is None:
            raise ValueError(f"煞星符号标签无法完整落在本宫：{value}")
        box = chosen
        px, py = box[0] + 10, (box[1] + box[3]) / 2
        xy = [(px - 580) / 492, (py - 580) / 492]
        draw.polygon(
            [
                (px * SCALE, (py - 6) * SCALE),
                ((px + 6) * SCALE, py * SCALE),
                (px * SCALE, (py + 6) * SCALE),
                ((px - 6) * SCALE, py * SCALE),
            ],
            fill="#de9d89",
        )
        text(draw, (box[0] + 24, box[1] + 7), value, 18, "#de9d89", stroke=2)
        reserved.append(box)
        layout.append(
            {
                "key": symbol["key"],
                "label": value,
                "box": list(box),
                "marker_xy": xy,
                "marker_box": [px - 9, py - 9, px + 9, py + 9],
                "kind": "symbolic",
                "branch": symbol["branch"],
                "placement": "inside_region",
                "display_profile": DISPLAY_PROFILE,
            }
        )


def render_ziwei_png(data):
    image = Image.new("RGB", (1680 * SCALE, 1510 * SCALE), "#101b25")
    draw = ImageDraw.Draw(image)
    text(draw, (38, 20), "星图 · 紫微星名", 38, "#f2e6c9")
    text(draw, (1638, 43), "北天极星盘 / 十二宫 / 视星等 · 本地测试", 19, "#b6c3c6", anchor="rt")
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
    layer = prepare_display_layer(data["palace_layer"])
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
    disk, layout = single_panel(objects, layer)
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
    text(draw, (1190, 1270), "浅线为地平线 · 命宫金边 · 身宫青边", 15, "#9eafa9")
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
        "北天极中心全天投影 · 半径为极距 · 坐标 ESA Hipparcos / NASA JPL DE440s · "
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
