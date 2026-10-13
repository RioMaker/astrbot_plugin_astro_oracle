"""星名就近排布；点不移动，文字避让并以低权重短线指向真实位置。"""

import math

from .ziwei_linear_theme import measure

PANEL = 1200
CENTER = 600
RADIUS = 520


def free_box(box, occupied):
    return all(box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1] for b in occupied)


def segment_hits_box(a, b, box):
    """线段是否穿过文字框内部；用于候选评分，不改变天文坐标。"""
    lo, hi = 0.0, 1.0
    for start, delta, minimum, maximum in (
        (a[0], b[0] - a[0], box[0], box[2]),
        (a[1], b[1] - a[1], box[1], box[3]),
    ):
        if abs(delta) < 1e-9:
            if not minimum < start < maximum:
                return False
        else:
            p, q = sorted(((minimum - start) / delta, (maximum - start) / delta))
            lo, hi = max(lo, p), min(hi, q)
            if lo >= hi:
                return False
    return lo < hi


def name_layout(rows):
    points = {
        r["key"]: [CENTER + r["observer_xy"][0] * RADIUS, CENTER + r["observer_xy"][1] * RADIUS]
        for r in rows
    }
    dots = [(p[0] - 12, p[1] - 12, p[0] + 12, p[1] + 12) for p in points.values()]
    reserved = [
        (560, 577, 640, 628),
        (540, 26, 660, 67),
        (540, 1139, 660, 1180),
        (12, 579, 110, 626),
        (1092, 579, 1192, 626),
    ]
    for fraction, value in (
        (1 / 6, "+60°"),
        (1 / 3, "+30°"),
        (1 / 2, "0° 地平线"),
        (2 / 3, "−30°"),
        (5 / 6, "−60°"),
    ):
        y = CENTER - RADIUS * fraction + 12
        reserved.append((CENTER + 5, y - 3, CENTER + measure(value, 15) + 18, y + 23))
    result = []
    for row in rows:
        primary = f"{row['number']} {row['name']}"
        secondary = row["target"] + (" *" if row["mapping"]["convention"] else "")
        width = max(measure(primary, 22), measure(secondary, 16)) + 10
        height = 50
        px, py = points[row["key"]]
        candidates = []
        for distance in (24, 38, 54, 72, 96, 124, 158, 196, 236):
            for degree in (0, 180, 45, 315, 135, 225, 90, 270, 30, 150, 210, 330):
                angle = math.radians(degree)
                dx, dy = math.cos(angle) * distance, math.sin(angle) * distance
                x = px + dx - (width if dx < -1 else width / 2 if abs(dx) < 1 else 0)
                y = py + dy - height / 2
                box = (x, y, x + width, y + height)
                if not (
                    14 <= x and x + width <= PANEL - 14 and 75 <= y and y + height <= PANEL - 75
                ):
                    continue
                if not free_box(box, reserved + dots):
                    continue
                endpoint = [min(max(px, x), x + width), min(max(py, y), y + height)]
                crosses = sum(segment_hits_box([px, py], endpoint, b) for b in reserved)
                crosses += sum(segment_hits_box(*label["leader_line"], box) for label in result)
                score = math.dist([px, py], endpoint) + distance * 0.08 + crosses * 65
                candidates.append((score, box, endpoint))
        if not candidates:
            raise ValueError(f"星名不能在真实星点附近完成避让：{row['name']}")
        _, box, endpoint = min(candidates, key=lambda c: c[0])
        reserved.append(box)
        result.append(
            {
                "key": row["key"],
                "name": row["name"],
                "number": row["number"],
                "primary": primary,
                "secondary": secondary,
                "box": list(box),
                "point_px": [px, py],
                "observer_xy": row["observer_xy"],
                "leader_line": [[px, py], endpoint],
            }
        )
    # 后加入的文字也可能挡住先前引线；完整排布后统一隐藏会穿字的线。
    # 关联仍保留同名与固定编号，天体点和文字位置不作事后挪动。
    for label in result:
        label["leader_visible"] = not any(
            segment_hits_box(*label["leader_line"], other) for other in reserved
        )
    return result
