"""星名优先整框留在真实方向所属研究宫；不能容纳时记录引线回退。"""

import math

from .image_renderer import SCALE
from .ziwei_palace_display import box_inside_palace, palace_label_candidates
from .ziwei_theme import font


def free_box(box, occupied):
    return all(box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1] for b in occupied)


def nearby_candidates(px, py, width, size):
    for distance in (18, 36, 55, 80, 112, 150, 195, 245, 300, 360):
        for angle in (0, 180, 45, 315, 135, 225, 90, 270):
            angle = math.radians(angle)
            dx, dy = distance * math.cos(angle), distance * math.sin(angle)
            x = px + dx - (width if dx < -1 else width / 2 if abs(dx) < 1 else 0)
            y = py + dy - size / 2
            box = (x - 3, y - 3, x + width + 3, y + size + 7)
            if 12 <= box[0] < box[2] <= 1148 and 80 <= box[1] < box[3] <= 1080:
                yield box


def choose_object_label(draw, obj, layer, region_map, occupied):
    value = obj["name"] + ("*" if obj["name"] == "紫微" else "")
    sector = next(s for s in layer["sectors"] if s["branch"] == obj["research_branch"])
    px, py = (580 + v * 492 for v in obj["display_xy"])
    sizes = (25, 23, 21) if obj["major"] else (17, 16, 15)
    for size in sizes:
        width = draw.textlength(value, font=font(size)) / SCALE
        candidates = list(nearby_candidates(px, py, width, size))
        candidates.extend(
            b
            for _, b, _ in palace_label_candidates(
                sector, width + 6, size + 10, preferred_dec=obj["dec_date_deg"]
            )
        )
        candidates.sort(
            key=lambda b: math.hypot(px - min(max(px, b[0]), b[2]), py - min(max(py, b[1]), b[3]))
        )
        for box in candidates:
            if free_box(box, occupied) and box_inside_palace(box, sector["branch"], region_map):
                return {
                    "key": obj["key"],
                    "label": value,
                    "box": list(box),
                    "branch": sector["branch"],
                    "kind": "object",
                    "font_size": size,
                    "placement": "inside_region",
                    "fallback_reason": None,
                }
    # 不移动真实星点或伪造归属：仅让文字回退，并保留原研究宫和明确原因。
    size = sizes[-1]
    width = draw.textlength(value, font=font(size)) / SCALE
    for box in nearby_candidates(px, py, width, size):
        if free_box(box, occupied):
            return {
                "key": obj["key"],
                "label": value,
                "box": list(box),
                "branch": sector["branch"],
                "kind": "object",
                "font_size": size,
                "placement": "leader_fallback",
                "fallback_reason": "home_region_full",
            }
    raise ValueError(f"星名标签无法避让：{value}")
