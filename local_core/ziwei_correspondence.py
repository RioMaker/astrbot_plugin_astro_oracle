"""只用同名编号关联传统落宫与观测方向，不将地支格强换成实测天区。"""

from .ziwei_traditional import traditional_core

PROFILE = "traditional-palace-and-observer-state-v2"
NORTH_SOURCE = "https://hk.space.museum/sc/web/spm/resources/teachers-corner/constellations-and-myths/chinese-starlore.html"
CORE_SOURCE = "https://zh.wikisource.org/w/index.php?oldid=1963110"
SHORT_TARGETS = {
    "紫微": "北极星",
    "天机": "斗宿四",
    "太阳": "太阳",
    "武曲": "开阳",
    "天同": "斗宿一",
    "廉贞": "玉衡",
    "天府": "斗宿六",
    "太阴": "月球",
    "贪狼": "天枢",
    "巨门": "天璇",
    "天相": "斗宿二",
    "天梁": "斗宿五",
    "七杀": "斗宿三",
    "破军": "瑶光",
    "禄存": "天玑",
    "文曲": "天权",
    "左辅": "Alcor",
}
NORTH_NAMES = {"贪狼", "巨门", "禄存", "文曲", "廉贞", "武曲", "破军"}


def mapping_info(obj):
    if obj["kind"] in {"sun", "moon"}:
        return {"class": "entity", "label": "实体日月", "source": CORE_SOURCE, "convention": False}
    if obj["name"] in NORTH_NAMES:
        return {
            "class": "historical_alias",
            "label": "北斗历史别名",
            "source": NORTH_SOURCE,
            "convention": False,
        }
    return {
        "class": "display_convention",
        "label": "展示约定",
        "source": "project:docs/ZIWEI_SKY_PREVIEW.md",
        "convention": True,
    }


def build_correspondence(data, leap_policy="quanshu_next"):
    traditional = traditional_core(data["palace_layer"]["assignment"], leap_policy)
    rows = []
    for obj in data["single_chart"]["objects"]:
        info = mapping_info(obj)
        pos = traditional["positions"][obj["name"]]
        rows.append(
            {
                "key": obj["key"],
                "name": obj["name"],
                "major": obj["major"],
                "target": SHORT_TARGETS[obj["name"]],
                "mapping": info,
                "traditional_branch": pos["branch"],
                "traditional_palace": pos["palace"],
                "altitude_deg": obj["altitude_deg"],
                "azimuth_deg": obj["azimuth_deg"],
                "magnitude": obj["magnitude"],
                "magnitude_estimated": obj["kind"] != "star",
                "hip": obj.get("hip"),
                "naif_id": obj.get("naif_id"),
                "observer_xy": list(obj["single_xy"]),
                "ra_date_deg": obj["ra_date_deg"],
                "dec_date_deg": obj["dec_date_deg"],
            }
        )
    return {
        "profile": PROFILE,
        "traditional": traditional,
        "rows": rows,
        "real_frame": "topocentric_horizontal_no_refraction",
        "association": "same_name_and_fixed_number_only",
        "boundary": "传统地支为安星格；真实侧只有高度方位，不推造真实宫位或统计同异。",
    }
