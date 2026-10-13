"""传统标签驱动的最近球面星种子分区；真实点不移动，不推称历史物理宫界。"""

import math

import numpy as np

from .ziwei_palaces import BRANCHES

PROFILE = "traditional-labelled-spherical-nearest-seed-v1"
FORMULA = "b(v,t)=traditional_branch(argmax_i v·v_i(t),t)"
BOUNDARY_FORMULA = "(v_i-v_j)·v=0, with both seeds maximal and different branches"
LIMITATION = (
    "这是传统安星标签驱动的球面关联表达模型，不是历史推导的物理宫界；"
    "同宫可有多片，无实体种子的宫不分配天区。"
)
OUTSIDE = -1
AMBIGUOUS = -2
# 只处理 double 运算带来的数值并列，不作为历表精度或天体重合的物理阈值。
TIE_SCORE_ATOL = 16 * np.finfo(np.float64).eps


def unit_vector(altitude_deg, azimuth_deg):
    """站心高度/方位转单位方向，分量依次为北、东、天顶。"""
    altitude, azimuth = float(altitude_deg), float(azimuth_deg)
    if not (math.isfinite(altitude) and math.isfinite(azimuth)):
        raise ValueError("球面方向必须为有限数值。")
    if not -90 <= altitude <= 90:
        raise ValueError("高度须在 -90° 至 +90°。")
    if abs(altitude) == 90:
        # 极点的方位角不定义独立方向，避免 cos(pi/2) 残差引入方位偏差。
        return np.array((0.0, 0.0, math.copysign(1.0, altitude)), dtype=np.float64)
    height, azimuth = math.radians(altitude), math.radians(azimuth % 360)
    vector = np.array(
        (
            math.cos(height) * math.cos(azimuth),
            math.cos(height) * math.sin(azimuth),
            math.sin(height),
        ),
        dtype=np.float64,
    )
    return vector / np.linalg.norm(vector)


def _seeds(rows):
    seeds = []
    for row in rows:
        branch = row["traditional_branch"]
        if not isinstance(branch, str) or len(branch) != 1 or branch not in BRANCHES:
            raise ValueError(f"未知传统地支：{branch}")
        seeds.append(
            (
                BRANCHES.index(branch),
                unit_vector(row["altitude_deg"], row["azimuth_deg"]),
            )
        )
    if not seeds:
        raise ValueError("球面关联分区至少需要一个实体种子。")
    return seeds


def _classify_components(seeds, north, east, up):
    """逐种子更新两个不同支的最高分，不生成 像素数×种子数 的分数数组。"""
    shape = np.broadcast_shapes(np.shape(north), np.shape(east), np.shape(up))
    best = np.full(shape, -np.inf, dtype=np.float64)
    second_branch = np.full(shape, -np.inf, dtype=np.float64)
    winner = np.full(shape, OUTSIDE, dtype=np.int16)
    for branch, seed in seeds:
        score = north * seed[0] + east * seed[1] + up * seed[2]
        different = winner != branch
        better = score > best
        # 换成另一个支时，原最高分就是新赢家之外的最高分。
        replace_branch = different & better
        second_branch[replace_branch] = best[replace_branch]
        other = different & ~better
        second_branch[other] = np.maximum(second_branch[other], score[other])
        best[better] = score[better]
        winner[better] = branch
    tied = np.isfinite(second_branch) & ((best - second_branch) <= TIE_SCORE_ATOL)
    winner[tied] = AMBIGUOUS
    return winner


def classify_direction(rows, altitude_deg, azimuth_deg):
    """返回最近种子的地支索引；不同支数值并列返回 -2，同支并列直接合并。"""
    vector = unit_vector(altitude_deg, azimuth_deg)
    return int(_classify_components(_seeds(rows), *vector).item())


def region_map(rows, size=1200, center=600, radius=520):
    """返回 int16 圆盘分区：圆外 -1、异支并列 -2，其余为 BRANCHES 索引。

    沿用天顶全天投影 r=(90-altitude)/180：北上东左、地平线 r=0.5。
    像素方向在球面上比较；圆心为天顶，外缘为天底的投影极限。
    同支的最近种子区域自动合并，不额外补出未采用实体种子的宫。
    """
    if not isinstance(size, int) or size <= 0:
        raise ValueError("分区图尺寸须为正整数。")
    center, radius = float(center), float(radius)
    if not (math.isfinite(center) and math.isfinite(radius)) or radius <= 0:
        raise ValueError("圆盘中心须为有限数值，半径须为有限正数。")
    seeds = _seeds(rows)
    ys, xs = np.ogrid[:size, :size]
    dx, dy = xs - center, ys - center
    distance = np.hypot(dx, dy)
    inside = distance <= radius
    radial = np.divide(distance, radius, out=np.zeros_like(distance), where=inside)
    horizontal = np.sin(math.pi * radial)
    horizontal[radial == 1] = 0.0
    away_from_center = inside & (distance > 0)
    north = np.divide(-dy, distance, out=np.zeros_like(distance), where=away_from_center)
    east = np.divide(-dx, distance, out=np.zeros_like(distance), where=away_from_center)
    north *= horizontal
    east *= horizontal
    up = np.cos(math.pi * radial)
    regions = _classify_components(seeds, north, east, up)
    regions[~inside] = OUTSIDE
    return regions


def boundary_mask(regions):
    """标出相邻有效且不同支的两侧像素；圆外和并列带不作为一个宫。"""
    regions = np.asarray(regions)
    if regions.ndim != 2:
        raise ValueError("宫区图须为二维数组。")
    valid = (regions >= 0) & (regions < len(BRANCHES))
    boundary = np.zeros(regions.shape, dtype=bool)
    horizontal = valid[:, :-1] & valid[:, 1:] & (regions[:, :-1] != regions[:, 1:])
    vertical = valid[:-1, :] & valid[1:, :] & (regions[:-1, :] != regions[1:, :])
    boundary[:, :-1] |= horizontal
    boundary[:, 1:] |= horizontal
    boundary[:-1, :] |= vertical
    boundary[1:, :] |= vertical
    return boundary
