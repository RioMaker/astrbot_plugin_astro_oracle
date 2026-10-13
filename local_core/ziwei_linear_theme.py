"""Linear 风格：Inter 英数与已有中文无衬线字形补全，静态 PNG 无装饰。"""

import io
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .image_renderer import SCALE

BG = "#0a0a0b"
SURFACE = "#121213"
INK = "#ffffff"
MUTED = "#a1a1aa"
LINE = (255, 255, 255, 26)
ACCENT = "#5e6ad2"
FONT_DIR = Path(__file__).resolve().parents[1] / "assets/fonts"
INTER = FONT_DIR / "AstroInter.ttf"
CJK = FONT_DIR / "AstroSans.otf"


def is_cjk(char):
    code = ord(char)
    return 0x2E80 <= code <= 0xA4CF or 0xF900 <= code <= 0xFAFF or 0xFF00 <= code <= 0xFFEF


@lru_cache(maxsize=48)
def font(size, chinese=False):
    return ImageFont.truetype(io.BytesIO((CJK if chinese else INTER).read_bytes()), size * SCALE)


def measure(value, size):
    return (
        sum(font(size, is_cjk(ch)).getlength(ch) / SCALE for ch in value)
        - max(0, len(value) - 1) * size * 0.01
    )


def text(draw, xy, value, size=18, color=INK, anchor="lt", strong=False):
    x, y = xy
    width = measure(value, size)
    if anchor.startswith("m"):
        x -= width / 2
    elif anchor.startswith("r"):
        x -= width
    if anchor.endswith("m"):
        y -= size / 2
    baseline = (y + size * 0.91) * SCALE
    for char in value:
        face = font(size, is_cjk(char))
        draw.text(
            (round(x * SCALE), round(baseline)),
            char,
            font=face,
            fill=color,
            anchor="ls",
            stroke_width=1 if strong else 0,
            stroke_fill=color,
        )
        x += face.getlength(char) / SCALE - size * 0.01


def box(draw, bounds, fill=SURFACE, radius=6, outline=LINE):
    draw.rounded_rectangle(
        tuple(round(v * SCALE) for v in bounds),
        radius=radius * SCALE,
        fill=fill,
        outline=outline,
        width=SCALE,
    )


def rule(draw, a, b, color=LINE):
    draw.line([tuple(round(v * SCALE) for v in p) for p in (a, b)], fill=color, width=SCALE)
