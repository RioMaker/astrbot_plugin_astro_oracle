"""真实星点的小编号布局；完整说明由十二宫卡片承载。"""

import math

from .image_renderer import SCALE
from .ziwei_chart import MAJOR_ORDER
from .ziwei_theme import font

OBJECT_ORDER = (*MAJOR_ORDER, "禄存", "文曲", "左辅")


def object_number(obj):
    return f"{OBJECT_ORDER.index(obj['name']) + 1:02d}"


def free_box(box, occupied):
    return all(box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1] for b in occupied)


def choose_number_marker(draw, obj, occupied):
    """只在星点附近安排编号；短关联线不承担宫位说明。"""
    value, size = object_number(obj), 14
    width = draw.textlength(value, font=font(size)) / SCALE
    px, py = (580 + v * 492 for v in obj["display_xy"])
    for distance in (17, 24, 32, 42, 54, 68, 84):
        for degree in (0, 180, 45, 315, 135, 225, 90, 270):
            angle = math.radians(degree)
            x, y = px + distance * math.cos(angle), py + distance * math.sin(angle)
            box = (x - width / 2 - 3, y - 11, x + width / 2 + 3, y + 11)
            if any(
                math.hypot(a - 580, b - 580) > 492
                for a in (box[0], box[2])
                for b in (box[1], box[3])
            ):
                continue
            if free_box(box, occupied):
                endpoint = [min(max(px, box[0]), box[2]), min(max(py, box[1]), box[3])]
                return {
                    "key": obj["key"],
                    "label": value,
                    "number": value,
                    "box": list(box),
                    "branch": obj["research_branch"],
                    "kind": "point_number",
                    "placement": "near_true_position",
                    "point_xy": list(obj["display_xy"]),
                    "leader_line": [[px, py], endpoint],
                }
    raise ValueError(f"真实星点编号无法在附近避让：{obj['name']}")
