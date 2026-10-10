"""用 fontTools 从经校验的 OFL 原字体重建独立 AstroSans 字体。"""

import argparse
import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

SOURCE_HASH = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError("原字体 SHA-256 与确认来源不符。")
    font = TTFont(args.source, recalcTimestamp=False)
    options = subset.Options()
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    options.name_legacy = True
    options.name_languages = [0x409]
    cutter = subset.Subsetter(options=options)
    codes = set()
    for start, end in (
        (0x20, 0x250),
        (0x2000, 0x2070),
        (0x3000, 0x3100),
        (0x4E00, 0xA000),
        (0xFF00, 0xFFF0),
    ):
        codes.update(range(start, end))
    codes.update(map(ord, "−≤°·"))
    cutter.populate(unicodes=codes)
    cutter.subset(font)
    for record in font["name"].names:
        if record.nameID in {1, 3, 4, 6}:
            record.string = "AstroSans".encode(record.getEncoding())
    if "CFF " in font:
        top = font["CFF "].cff.topDictIndex[0]
        top.FamilyName = top.FullName = "AstroSans"
        font["CFF "].cff.fontNames = ["AstroSans"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "AstroSans.otf"
    font.save(target)
    font.close()
    record = {
        "source": "https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/"
        "SimplifiedChinese/NotoSansCJKsc-Regular.otf",
        "source_sha256": SOURCE_HASH,
        "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "output_bytes": target.stat().st_size,
        "license": "SIL Open Font License 1.1; see LICENSE.txt",
        "modification": "Subset of Latin, common CJK, kana and display punctuation; "
        "renamed AstroSans; original copyright retained in font metadata.",
    }
    (OUTPUT / "provenance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
