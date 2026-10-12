"""北天极宫位星盘的区域底色、地平线与文字归属；不改变安宫和天体状态。"""

import math

import numpy as np
from PIL import Image

from .ziwei_palaces import BRANCHES, project_north_pole
from .ziwei_theme import background

DISPLAY_PROFILE = "witchcore-north-pole-palace-wheel-v2"
PANEL_WIDTH = 1160
CENTER = 580
RADIUS = 492


def right_ascension_at_xy(x, y):
    """从北天极中心图面还原日期真赤经；输入是单位圆坐标。"""
    return np.degrees(np.arctan2(-np.asarray(x), -np.asarray(y))) % 360


def altitude_at_xy(x, y, context):
    """把图面方向换算成观测点高度；明暗由真实地平线划分。"""
    ra = right_ascension_at_xy(x, y)
    dec = np.radians(90 - 180 * np.hypot(x, y))
    latitude = math.radians(context["latitude_deg"])
    hour = np.radians(context["sidereal_deg"] - ra)
    up = np.sin(dec) * math.sin(latitude) + np.cos(dec) * math.cos(latitude) * np.cos(hour)
    return np.degrees(np.arcsin(np.clip(up, -1, 1)))


def sector_ids_at_xy(x, y, layer):
    """返回零基地支编号；单位圆外为 -1，宫界起点含在本宫中。"""
    ra = right_ascension_at_xy(x, y)
    starts = np.array([s["start_ra_deg"] for s in layer["sectors"]])
    branches = np.array([BRANCHES.index(s["branch"]) for s in layer["sectors"]], dtype=np.int8)
    index = (np.searchsorted(starts, ra, side="right") - 1) % len(starts)
    return np.where(np.hypot(x, y) <= 1, branches[index], -1).astype(np.int8)


def palace_region_map(layer):
    """逻辑像素中心的区域归属图，兼用于底色和完整文字框包含检查。"""
    axis = (np.arange(PANEL_WIDTH) + 0.5 - CENTER) / RADIUS
    return sector_ids_at_xy(axis[None, :], axis[:, None], layer)


def palace_background(layer, region_map):
    image = np.array(background(PANEL_WIDTH, PANEL_WIDTH, y_offset=176))
    axis = (np.arange(PANEL_WIDTH) + 0.5 - CENTER) / RADIUS
    bright = altitude_at_xy(axis[None, :], axis[:, None], layer["projection_context"]) >= 0
    for index, sector in enumerate(layer["sectors"]):
        branch = BRANCHES.index(sector["branch"])
        inside, outside = (
            ((39, 24, 52), (16, 12, 24)) if index % 2 == 0 else ((47, 26, 57), (22, 14, 29))
        )
        if sector["name"] == "命宫":
            inside, outside = (57, 43, 31), (31, 24, 25)
        elif sector["body"]:
            inside, outside = (25, 44, 37), (15, 26, 23)
        selected = region_map == branch
        image[selected & bright] = inside
        image[selected & ~bright] = outside
    return Image.fromarray(image)


def box_inside_palace(box, branch, region_map):
    """含留白的完整矩形须属于本宫，不能只检查文字中心。"""
    x1, y1, x2, y2 = box
    left, top, right, bottom = math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2)
    if not (0 <= left < right <= PANEL_WIDTH and 0 <= top < bottom <= PANEL_WIDTH):
        return False
    return bool(np.all(region_map[top:bottom, left:right] == BRANCHES.index(branch)))


def palace_label_candidates(sector, width, height, preferred_dec=-55):
    """在本宫不同赤纬和宫宽位置取候选；按目标环带距离排序，次序可复算。"""
    anchor = project_north_pole(
        (sector["start_ra_deg"] + sector["span_deg"] / 2) % 360, preferred_dec
    )
    candidates = []
    for fraction in (0.5, 0.35, 0.65, 0.2, 0.8):
        ra = (sector["start_ra_deg"] + sector["span_deg"] * fraction) % 360
        for dec in range(-80, 81, 4):
            xy = project_north_pole(ra, dec)
            px, py = CENTER + xy[0] * RADIUS, CENTER + xy[1] * RADIUS
            box = (px - width / 2, py - height / 2, px + width / 2, py + height / 2)
            score = math.dist(xy, anchor) * RADIUS + abs(fraction - 0.5) * 20
            candidates.append((score, box, xy))
    return sorted(candidates, key=lambda candidate: candidate[0])


def prepare_display_layer(layer):
    """只转换界线和符号的图面位置；原始模型、宫名和安星数据不原地修改。"""
    sectors = [
        {**sector, "curves": [[[0, 0], project_north_pole(sector["start_ra_deg"], -90)]]}
        for sector in layer["sectors"]
    ]
    symbols = []
    for symbol in layer["symbolic_malefics"]:
        sector = next(s for s in sectors if s["branch"] == symbol["branch"])
        ra = (sector["start_ra_deg"] + sector["span_deg"] / 2) % 360
        symbols.append(
            {
                **symbol,
                "layout_options": [
                    project_north_pole(ra, dec)
                    for dec in (25, -25, 45, -45, 65, -65, 80, -80, 10, -10)
                ],
            }
        )
    return {**layer, "sectors": sectors, "symbolic_malefics": symbols}


def horizon_curves(layer):
    """真实地平线投到星盘；经过南天极时切断外缘跳线。"""
    context = layer["projection_context"]
    phi = math.radians(context["latitude_deg"])
    curves, current = [], []
    for degree in range(721):
        az = math.radians(degree / 2)
        dec = math.degrees(math.asin(math.cos(phi) * math.cos(az)))
        hour = math.degrees(math.atan2(-math.sin(az), -math.sin(phi) * math.cos(az)))
        ra = (context["sidereal_deg"] - hour) % 360
        xy = project_north_pole(ra, dec)
        if current and math.dist(current[-1], xy) > 0.15:
            if len(current) > 1:
                curves.append(current)
            current = []
        current.append(xy)
    if len(current) > 1:
        curves.append(current)
    return curves
