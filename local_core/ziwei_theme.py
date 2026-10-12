"""附件 Witchcore 风格的静态 PNG 适配；装饰不代表天文数据。"""

import io
import math
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .image_renderer import SCALE

STYLE_PROFILE = "witchcore-palace-ledger-v2"
PURPLE = "#4a1942"
MIDNIGHT = "#0d0b14"
GOLD = "#c9a74e"
AMETHYST = "#7b68ae"
HERB = "#3d8b6e"
# 小字在午夜底色上使用同色相的较亮色阶，保留可读性。
SECONDARY = "#b6a5d0"
DIM_GOLD = "#ac925c"
FONT = Path(__file__).resolve().parents[1] / "assets/fonts/AstroSerif.otf"


@lru_cache(maxsize=24)
def font(size):
    return ImageFont.truetype(io.BytesIO(FONT.read_bytes()), size * SCALE)


def text(draw, xy, value, size, color=GOLD, anchor="lt", stroke=0):
    draw.text(
        tuple(round(v * SCALE) for v in xy),
        value,
        font=font(size),
        fill=color,
        anchor=anchor,
        stroke_width=stroke * SCALE,
        stroke_fill=MIDNIGHT,
    )


def fitted_text(draw, xy, value, size, color, max_width):
    while value and draw.textlength(value, font=font(size)) > max_width * SCALE:
        value = value[:-2] + "…" if len(value) > 2 else ""
    text(draw, xy, value, size, color)


def background(width, height, y_offset=0, total_height=1510, scale=1):
    """精确深紫到午夜黑的纵向渐变，叠加低强度径向微光。"""
    y = (np.arange(height * scale, dtype=np.float32) / scale + y_offset) / total_height
    start, end = np.array([74, 25, 66], dtype=np.float32), np.array([13, 11, 20], dtype=np.float32)
    colors = start[None, :] * (1 - y[:, None]) + end[None, :] * y[:, None]
    pixels = np.broadcast_to(colors[:, None, :], (height * scale, width * scale, 3)).copy()
    xx = np.arange(width * scale, dtype=np.float32)[None, :] / scale
    yy = np.arange(height * scale, dtype=np.float32)[:, None] / scale + y_offset
    glow = np.exp(-((xx - 580) ** 2 + (yy - 640) ** 2) / (2 * 310**2))
    pixels += glow[:, :, None] * np.array([8, 3, 9])
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def stardust(image):
    """仅在星盘外留白绘制确定性的装饰星尘，不充当背景恒星。"""
    draw = ImageDraw.Draw(image, "RGBA")
    rng = random.Random(412)
    for _ in range(230):
        x, y = rng.uniform(22, image.width / SCALE - 22), rng.uniform(12, image.height / SCALE - 22)
        if math.hypot(x - 580, y - 756) < 520 or (x > 1170 and 176 < y < 1328):
            continue
        r = rng.choice([0.6, 0.8, 1.1]) * SCALE
        px, py = x * SCALE, y * SCALE
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(201, 167, 78, rng.randrange(25, 80)))


def card(image, box):
    """方角塔罗纸牌式细金边、暗色内底与柔和外阴影。"""
    bounds = tuple(round(v * SCALE) for v in box)
    padding = 24 * SCALE
    origin = (max(0, bounds[0] - padding), max(0, bounds[1] - padding))
    end = (min(image.width, bounds[2] + padding), min(image.height, bounds[3] + padding))
    shadow = Image.new("RGBA", (end[0] - origin[0], end[1] - origin[1]))
    local_bounds = (
        bounds[0] - origin[0],
        bounds[1] - origin[1],
        bounds[2] - origin[0],
        bounds[3] - origin[1],
    )
    ImageDraw.Draw(shadow).rectangle(local_bounds, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8 * SCALE))
    image.paste(shadow, origin, shadow)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle(bounds, fill=(13, 11, 20, 230), outline=(201, 167, 78, 77), width=SCALE)
    x1, y1, x2, y2 = box
    for x, dx in ((x1 + 6, 1), (x2 - 6, -1)):
        for y, dy in ((y1 + 6, 1), (y2 - 6, -1)):
            draw.line(
                [
                    (x * SCALE, (y + dy * 14) * SCALE),
                    (x * SCALE, y * SCALE),
                    ((x + dx * 14) * SCALE, y * SCALE),
                ],
                fill=(201, 167, 78, 130),
                width=SCALE,
            )


def rune_title(image, xy, value, size=40):
    ink = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(ink)
    x, y = xy
    for char in value:
        text(draw, (x, y), char, size, GOLD)
        x += draw.textlength(char, font=font(size)) / SCALE + 3
    glow = ink.filter(ImageFilter.GaussianBlur(4 * SCALE))
    glow.putalpha(glow.getchannel("A").point(lambda a: round(a * 0.4)))
    image.paste(glow, (0, 0), glow)
    image.paste(ink, (0, 0), ink)


def moon_ornament(draw, anchor_x=1480):
    """三个装饰月相，不绑定观测时刻。"""
    for i in range(3):
        x, y, r = (anchor_x + i * 48) * SCALE, 120 * SCALE, 10 * SCALE
        draw.ellipse((x - r, y - r, x + r, y + r), outline=GOLD, width=SCALE)
        if i != 1:
            offset = 5 * SCALE if i == 0 else -5 * SCALE
            draw.ellipse((x - r + offset, y - r, x + r + offset, y + r), fill=PURPLE)
    text(draw, (anchor_x - 10, 144), "月 相 纹 饰", 12, SECONDARY)
