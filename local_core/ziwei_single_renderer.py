"""紫微星名的北天极星盘；宫区显示与真实明暗分开。"""

import io
import math
from datetime import datetime

from PIL import Image, ImageDraw

from .image_renderer import SCALE, visual_style
from .ziwei_label_layout import choose_number_marker, object_number
from .ziwei_palace_display import (
    DISPLAY_PROFILE,
    box_inside_palace,
    horizon_curves,
    palace_background,
    palace_label_candidates,
    palace_region_map,
    prepare_display_layer,
)
from .ziwei_palace_ledger import HEIGHT, WIDTH, draw_palace_ledger
from .ziwei_theme import (
    DIM_GOLD,
    GOLD,
    HERB,
    SECONDARY,
    STYLE_PROFILE,
    background,
    card,
    fitted_text,
    font,
    moon_ornament,
    rune_title,
    stardust,
    text,
)

MAIN = GOLD
AUX = SECONDARY


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

    circle(center * SCALE, center * SCALE, radius, outline=GOLD, width=SCALE)
    circle(center * SCALE, center * SCALE, radius + 7, outline=(201, 167, 78, 80), width=SCALE)
    for degree in range(0, 360, 5):
        angle = math.radians(degree)
        draw.line(
            [
                point((-r * math.sin(angle), -r * math.cos(angle)))
                for r in (1.004, 1.014 if degree % 30 == 0 else 1.009)
            ],
            fill=(201, 167, 78, 120),
            width=SCALE,
        )
    circle(center * SCALE, center * SCALE, radius / 2, outline="#7b68ae", width=SCALE)
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
                outline=(123, 104, 174, 75),
                width=SCALE,
            )
        text(draw, (center + 6, center - radius * fraction + 9), label, 14, SECONDARY)
    for az in range(0, 360, 30):
        angle = math.radians(az)
        draw.line(
            [point((0, 0)), point((math.sin(angle), -math.cos(angle)))],
            fill=(201, 167, 78, 28),
            width=SCALE,
        )
    for index, sector in enumerate(sectors):
        previous = sectors[(index - 1) % len(sectors)]
        if sector["name"] == "命宫" or previous["name"] == "命宫":
            color, width = (201, 167, 78, 190), 2 * SCALE
        elif sector["body"] or previous["body"]:
            color, width = (61, 139, 110, 185), 2 * SCALE
        else:
            color, width = (201, 167, 78, 77), SCALE
        for curve in sector["curves"]:
            draw.line([point(xy) for xy in curve], fill=color, width=width)
    for curve in horizon_curves(layer):
        for index, (a, b) in enumerate(zip(curve, curve[1:])):
            if index % 12 < 8:
                draw.line([point(a), point(b)], fill=(182, 165, 208, 130), width=SCALE)
    for xy, value in (
        ((580, 54), "00h"),
        ((54, 580), "06h"),
        ((1106, 580), "18h"),
        ((580, 1106), "12h"),
    ):
        text(draw, xy, value, 22, GOLD, anchor="mm")
    text(draw, (580, 598), "北天极", 15, SECONDARY, anchor="mm")
    text(draw, (580, 1140), "外缘为南天极极限 · 方位环为日期真赤经", 15, SECONDARY, anchor="mm")
    dots = []
    for obj in objects:
        px, py = point(obj["display_xy"])
        dots.append((px / SCALE - 10, py / SCALE - 10, px / SCALE + 10, py / SCALE + 10))
        bright = obj["display_state"] == "bright"
        color = MAIN if obj["major"] else AUX
        if obj["kind"] == "star":
            r, alpha = visual_style(obj["magnitude"])
            circle(px, py, r, fill=(221, 197, 133, round(alpha * (255 if bright else 115))))
        else:
            circle(px, py, 4, outline=color if bright else DIM_GOLD, width=SCALE)
            if obj["kind"] == "sun":
                for angle in range(0, 360, 45):
                    angle = math.radians(angle)
                    draw.line(
                        [
                            (px + r * SCALE * math.cos(angle), py + r * SCALE * math.sin(angle))
                            for r in (9, 13)
                        ],
                        fill=color if bright else DIM_GOLD,
                        width=SCALE,
                    )
        circle(px, py, 8 if obj["major"] else 5, outline=color if bright else DIM_GOLD, width=SCALE)
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
    markers = []
    for obj in sorted(objects, key=object_number):
        label = choose_number_marker(draw, obj, reserved + dots)
        a, b = label["leader_line"]
        draw.line(
            [tuple(v * SCALE for v in a), tuple(v * SCALE for v in b)],
            fill=(201, 167, 78, 45),
            width=SCALE,
        )
        reserved.append(label["box"])
        label["style_profile"] = STYLE_PROFILE
        layout.append(label)
        markers.append(label)
    for label in markers:
        x1, y1, x2, y2 = label["box"]
        text(
            draw,
            ((x1 + x2) / 2, (y1 + y2) / 2),
            label["number"],
            14,
            SECONDARY,
            anchor="mm",
            stroke=1,
        )
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
            border, color = GOLD, GOLD
        elif sector["body"]:
            border, color = HERB, "#9fbdad"
        else:
            border, color = "#776137", GOLD
        draw.rectangle(
            tuple(v * SCALE for v in box),
            fill=(13, 11, 20, 235),
            outline=border,
            width=SCALE,
        )
        text(draw, (x + 10, y + 8), value, size, color)
        text(draw, (x + 10, y + 34), subtitle, 13, "#9fbdad" if sector["body"] else SECONDARY)
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


def render_ziwei_png(data):
    image = background(WIDTH, HEIGHT, scale=SCALE)
    stardust(image)
    card(image, (26, 1342, WIDTH - 26, 1485))
    rune_title(image, (38, 20), "星轨神谕 · 紫微星图", 40)
    draw = ImageDraw.Draw(image)
    moon_ornament(draw, anchor_x=1960)
    text(draw, (WIDTH - 42, 43), "真实方位 / 十二宫说明 · 本地测试", 19, SECONDARY, anchor="rt")
    moment = datetime.fromisoformat(data["epoch_local"])
    site = data["site"]
    fitted_text(
        draw,
        (38, 71),
        f"{site['label']} · {moment:%Y-%m-%d %H:%M:%S %z} · {data['timezone']}",
        21,
        GOLD,
        1780,
    )
    fitted_text(
        draw,
        (38, 103),
        f"纬度 {site['latitude']:.5f}° / 经度 {site['longitude']:.5f}° · {data['time_note']}",
        17,
        SECONDARY,
        1780,
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
    fitted_text(draw, (38, 133), value, 16, SECONDARY, 1780)
    disk, layout = single_panel(objects, layer)
    image.paste(disk, (0, 176 * SCALE))
    ledger = draw_palace_ledger(image, objects, layer)
    draw = ImageDraw.Draw(image)
    text(draw, (38, 180), "真实星点 · 方位盘", 24, GOLD)
    text(draw, (38, 216), "小编号识别星点 · 紫色虚线为地平线（高度 0°）", 14, SECONDARY)
    text(draw, (1172, 177), "十二宫 · 星曜说明", 26, GOLD)
    text(
        draw,
        (1172, 215),
        "按宫位阅读 · 编号对应左盘 · 方位角：北 0° / 东 90° / 南 180° / 西 270°",
        14,
        SECONDARY,
    )
    notes = [
        (
            "左盘星点保持真实坐标，编号仅用于识别；右侧说明按所属研究宫分组。"
            "短关联线降低权重，六煞仅在宫卡中标 [符]。",
            GOLD,
        ),
        (
            "高度 ≥ 0° 为明区，< 0° 为暗区；不等同于斗数庙旺或实际可见性。"
            "V 等越小越亮，~ 为估算；未计大气、云、食与背景。",
            SECONDARY,
        ),
        (
            "* 紫微采用现代北极星展示约定 · 坐标 ESA Hipparcos / NASA JPL DE440s · "
            "地点 GeoNames CC BY 4.0 · 盘外星尘与月相为装饰",
            SECONDARY,
        ),
        (
            "宫界是晋书宿度的今星锚定研究示意，并非已认证古宫界；"
            "事项宫按当地民用时安置。金色为主星，紫水晶色为辅星。",
            SECONDARY,
        ),
    ]
    for index, (value, color) in enumerate(notes):
        text(draw, (38, 1355 + index * 32), value, 15, color)
    output = io.BytesIO()
    image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(output, format="PNG")
    return output.getvalue(), {"single": layout, "palace_ledger": ledger}
