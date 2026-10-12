"""从固定 OFL 来源裁剪并重命名本地紫微预览使用的衬线字体。"""

import argparse
import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

SOURCE_HASH = "2a2eae2628df83556c54018c41e20fa532c1b862c5256ae8b3f23feb918d12ca"
REVISION = "f8d157532fbfaeda587e826d4cd5b21a49186f7c"
SOURCE = (
    f"https://github.com/notofonts/noto-cjk/blob/{REVISION}/Serif/OTF/"
    "SimplifiedChinese/NotoSerifCJKsc-Regular.otf"
)
OUTPUT = Path(__file__).resolve().parents[1] / "assets/fonts"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("license", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError("原字体 SHA-256 与固定来源不符。")
    face = TTFont(args.source, recalcTimestamp=False)
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
    codes.update(map(ord, "−≤≥°·αβγδζηστφμ"))
    cutter.populate(unicodes=codes)
    cutter.subset(face)
    for record in face["name"].names:
        if record.nameID in {1, 3, 4, 6}:
            record.string = "AstroSerif".encode(record.getEncoding())
    top = face["CFF "].cff.topDictIndex[0]
    top.FamilyName = top.FullName = "AstroSerif"
    face["CFF "].cff.fontNames = ["AstroSerif"]
    target = OUTPUT / "AstroSerif.otf"
    face.save(target)
    face.close()
    (OUTPUT / "SERIF_LICENSE.txt").write_bytes(args.license.read_bytes())
    record = {
        "source": SOURCE,
        "revision": REVISION,
        "source_sha256": SOURCE_HASH,
        "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "output_bytes": target.stat().st_size,
        "license": "SIL Open Font License 1.1; see SERIF_LICENSE.txt",
        "modification": "Subset of Latin, common CJK and display punctuation; "
        "renamed AstroSerif; original copyright retained in font metadata.",
    }
    (OUTPUT / "serif_provenance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
