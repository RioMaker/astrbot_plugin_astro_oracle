"""从固定官方 Inter 4.1 静态字体重建本地 Linear 预览用字库。"""

import argparse
import hashlib
import json
from pathlib import Path

import fontTools
from fontTools import subset
from fontTools.ttLib import TTFont

RELEASE = "v4.1"
REVISION = "e3a3d4c57d5ecc01453a575621882a384c1995a3"
SOURCE = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
ARCHIVE_HASH = "9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e"
SOURCE_HASH = "40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82"
LICENSE_HASH = "262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FAMILY = "AstroUISans"
REQUIRED = "→±≥≤°·—↑↓αβγδζηστφμ"
RANGES = (
    (0x0020, 0x0300),  # ASCII, Latin and phonetic extensions
    (0x0300, 0x0530),  # Combining marks, Greek and Cyrillic
    (0x1E00, 0x2000),  # Extended Latin and Greek
    (0x2000, 0x2150),  # Punctuation, superscripts, currency and letterlike symbols
    (0x2190, 0x2300),  # Arrows and mathematical operators
    (0x25A0, 0x2700),  # Geometric shapes and miscellaneous symbols
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="官方压缩包内 extras/ttf/Inter-Regular.ttf")
    parser.add_argument("license", type=Path, help="同一官方压缩包内 LICENSE.txt")
    args = parser.parse_args()
    if sha256(args.source) != SOURCE_HASH:
        raise ValueError("原字体 SHA-256 与固定官方版本不符。")
    if sha256(args.license) != LICENSE_HASH:
        raise ValueError("许可 SHA-256 与固定官方版本不符。")

    face = TTFont(args.source, recalcTimestamp=False)
    codes = {code for start, end in RANGES for code in range(start, end)}
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    cutter = subset.Subsetter(options=options)
    cutter.populate(unicodes=codes)
    cutter.subset(face)
    # Inter is a Reserved Font Name. Rename the derivative's family and instance
    # identifiers while preserving the source's copyright and OFL metadata.
    names = {
        1: FAMILY,
        2: "Regular",
        3: f"{REVISION};{FAMILY}-Regular",
        4: f"{FAMILY} Regular",
        6: f"{FAMILY}-Regular",
        16: FAMILY,
        17: "Regular",
        21: FAMILY,
        22: "Regular",
    }
    for name in face["name"].names:
        if name.nameID in names:
            name.string = names[name.nameID].encode(name.getEncoding())

    cmap = face.getBestCmap()
    required_codes = set(range(0x20, 0x7F)) | set(map(ord, REQUIRED))
    missing = sorted(required_codes - cmap.keys())
    if missing:
        raise ValueError(f"必要显示字符缺失: {missing}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "AstroInter.ttf"
    face.save(target)
    face.close()
    (OUTPUT / "LINEAR_LICENSE.txt").write_bytes(args.license.read_bytes())

    record = {
        "source": SOURCE,
        "archive_member": "extras/ttf/Inter-Regular.ttf",
        "release": RELEASE,
        "revision": REVISION,
        "revision_url": f"https://github.com/rsms/inter/tree/{REVISION}",
        "archive_sha256": ARCHIVE_HASH,
        "source_sha256": SOURCE_HASH,
        "source_bytes": args.source.stat().st_size,
        "source_family": "Inter",
        "source_subfamily": "Regular",
        "output_sha256": sha256(target),
        "output_bytes": target.stat().st_size,
        "output_file": target.name,
        "family": FAMILY,
        "subfamily": "Regular",
        "weight_class": 400,
        "fonttools_version": fontTools.__version__,
        "license": "SIL Open Font License 1.1; see LINEAR_LICENSE.txt",
        "license_sha256": LICENSE_HASH,
        "modification": (
            "Subset of Latin, Greek, Cyrillic, combining marks, punctuation, "
            "arrows, mathematical operators and display symbols; renamed "
            "AstroUISans to avoid the Reserved Font Name Inter. Original "
            "copyright and license metadata retained."
        ),
        "unicode_ranges": [f"U+{start:04X}-U+{end - 1:04X}" for start, end in RANGES],
        "mapped_codepoints": len(cmap),
        "required_symbols": REQUIRED,
        "cjk_codepoints": sum(0x4E00 <= code <= 0x9FFF for code in cmap),
        "cjk_fallback": "Existing bundled AstroSans.otf; not glyphs from Inter.",
        "runtime": "Static TrueType font; Pillow FreeType; no system font required.",
    }
    (OUTPUT / "linear_provenance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=True))


if __name__ == "__main__":
    main()
