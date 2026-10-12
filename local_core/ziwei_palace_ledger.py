"""十二宫说明卡片：标题明确归属，小编号与真实星点建立弱关联。"""

from PIL import ImageDraw

from .image_renderer import SCALE
from .ziwei_label_layout import object_number
from .ziwei_palaces import BRANCHES, PALACES
from .ziwei_theme import GOLD, HERB, SECONDARY, card, text

LEDGER_PROFILE = "palace-cards-numbered-sky-v1"
WIDTH, HEIGHT = 2160, 1510
LEFT, TOP, RIGHT, BOTTOM = 1172, 244, 2128, 1320
GAP = 12


def palace_groups(objects, layer):
    """只分组，不改变天空坐标、事项宫安置或六煞数据。"""
    groups = []
    for sector in layer["sectors"]:
        branch = sector["branch"]
        groups.append(
            {
                "sector": sector,
                "objects": sorted(
                    [o for o in objects if o["research_branch"] == branch], key=object_number
                ),
                "symbols": [s for s in layer["symbolic_malefics"] if s["branch"] == branch],
            }
        )
    if layer["assignment"]["available"]:
        return sorted(groups, key=lambda g: PALACES.index(g["sector"]["name"]))
    return sorted(groups, key=lambda g: BRANCHES.index(g["sector"]["branch"]))


def ledger_cards(objects, layer):
    groups = palace_groups(objects, layer)
    rows = [groups[i : i + 3] for i in range(0, 12, 3)]
    heights = [
        max(
            108
            + len(g["objects"]) * 25
            + (24 * ((len(g["symbols"]) + 2) // 3) + 12 if g["symbols"] else 0)
            for g in row
        )
        for row in rows
    ]
    extra = (BOTTOM - TOP - 3 * GAP - sum(heights)) / 4
    if extra < 0:
        raise ValueError("十二宫说明卡片内容超出可读布局容量。")
    width = (RIGHT - LEFT - 2 * GAP) / 3
    cards = []
    y = TOP
    for row, height in zip(rows, heights):
        for col, group in enumerate(row):
            x = LEFT + col * (width + GAP)
            cards.append({**group, "box": [x, y, x + width, y + height + extra]})
        y += height + extra + GAP
    return cards


def draw_palace_ledger(image, objects, layer):
    cards = ledger_cards(objects, layer)
    for entry in cards:
        card(image, entry["box"])
    draw = ImageDraw.Draw(image, "RGBA")
    layout = []
    for entry in cards:
        sector = entry["sector"]
        x1, y1, x2, y2 = entry["box"]
        branch = sector["branch"]
        title = f"{sector['name']} · {branch}"
        body = " · 命身" if sector["body"] and sector["name"] == "命宫" else " · 身宫"
        subtitle = sector["ci"] + (body if sector["body"] else "")
        color = "#9fbdad" if sector["body"] and sector["name"] != "命宫" else GOLD
        if sector["name"] == "命宫" or sector["body"]:
            draw.rectangle(
                tuple(v * SCALE for v in entry["box"]),
                outline=GOLD if sector["name"] == "命宫" else HERB,
                width=SCALE,
            )
        text(draw, (x1 + 15, y1 + 12), title, 22, color)
        text(draw, (x2 - 15, y1 + 17), subtitle, 13, SECONDARY, anchor="rt")
        layout.append(
            {
                "key": f"palace:{branch}",
                "label": title,
                "box": [x1 + 12, y1 + 9, x2 - 12, y1 + 44],
                "card_box": entry["box"],
                "branch": branch,
                "kind": "palace",
                "placement": "palace_card",
            }
        )
        y = y1 + 55
        if entry["objects"]:
            for offset, heading in (
                (15, "号"),
                (46, "星名"),
                (119, "V等"),
                (182, "高度°"),
                (252, "方位°"),
            ):
                text(draw, (x1 + offset, y), heading, 12, SECONDARY)
            y += 25
            for obj in entry["objects"]:
                number = object_number(obj)
                text(draw, (x1 + 15, y + 3), number, 14, SECONDARY)
                name = obj["name"] + ("*" if obj["name"] == "紫微" else "")
                text(
                    draw,
                    (x1 + 46, y),
                    name,
                    21 if obj["major"] else 18,
                    GOLD if obj["major"] else SECONDARY,
                )
                estimate = "~" if obj["kind"] != "star" else ""
                for offset, value in (
                    (119, f"{estimate}{obj['magnitude']:+.1f}"),
                    (182, f"{obj['altitude_deg']:+.1f}"),
                    (252, f"{obj['azimuth_deg']:.1f}"),
                ):
                    text(draw, (x1 + offset, y + 3), value, 14, SECONDARY)
                layout.append(
                    {
                        "key": obj["key"],
                        "label": name,
                        "number": number,
                        "box": [x1 + 12, y - 2, x2 - 12, y + 22],
                        "card_box": entry["box"],
                        "branch": branch,
                        "kind": "object",
                        "placement": "palace_card",
                    }
                )
                y += 25
        else:
            text(draw, (x1 + 15, y + 9), "本图无选定真实天体", 15, SECONDARY)
            y += 47
        if entry["symbols"]:
            rows = (len(entry["symbols"]) + 2) // 3
            symbol_y = y2 - 16 - rows * 23
            draw.line(
                [
                    ((x1 + 15) * SCALE, (symbol_y - 9) * SCALE),
                    ((x2 - 15) * SCALE, (symbol_y - 9) * SCALE),
                ],
                fill=(201, 167, 78, 80),
                width=SCALE,
            )
            for index, symbol in enumerate(entry["symbols"]):
                row = index // 3
                sx, sy = x1 + 15 + index % 3 * 90, symbol_y + row * 23
                text(draw, (sx, sy), symbol["name"] + "[符]", 14, GOLD)
                layout.append(
                    {
                        "key": symbol["key"],
                        "label": symbol["name"] + "[符]",
                        "box": [sx - 2, sy - 2, sx + 80, sy + 19],
                        "card_box": entry["box"],
                        "branch": branch,
                        "kind": "symbolic",
                        "placement": "palace_card",
                    }
                )
    return layout
