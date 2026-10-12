"""紫微星名的真实天体预览；独立于已注册的 AstrBot 指令与服务。"""

import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path

from skyfield.api import wgs84
from skyfield.errors import EphemerisRangeError

from .bot_commands import ChartSettings, parse_request, resolve_place, resolve_time
from .sky_chart import clipped_arc, direction, project

PROFILE_VERSION = "ziwei-real-sky-preview-v2"
SOURCES = {
    "north": "https://www.gsstk.org.tw/?act=menuinfo&cmd=detail&mi_id=20201021054"
    "&ml_id=20201021010",
    "south": "https://www.gsstk.org.tw/?act=menuinfo&cmd=detail&mi_id=20201021055"
    "&ml_id=20201021010",
    "chinese_ids": "https://github.com/Stellarium/stellarium/blob/master/skycultures/"
    "chinese/index.json",
    "pole": "https://www.daoist.org/BookSearch(test)/list013/133.pdf",
}

# 南斗采用本次明确列出的拜耳星标识，不能将占星顺序直接当作斗宿编号。
# 这是传统星名的展示约定，不是紫微斗数十二宫的安星算法。
# 名称、HIP、天文名称、主星、分组、对应性质。
CATALOG = (
    ("紫微", 11767, "勾陈一 / α UMi", True, "pole", "现代北极星展示约定"),
    ("天机", 92855, "斗宿四 / σ Sgr", True, "south", "南斗星名展示约定"),
    ("武曲", 65378, "开阳 / ζ UMa", True, "north", "北斗传统别名"),
    ("天同", 92041, "斗宿一 / φ Sgr", True, "south", "南斗星名展示约定"),
    ("廉贞", 62956, "玉衡 / ε UMa", True, "north", "北斗传统别名"),
    ("天府", 93506, "斗宿六 / ζ Sgr", True, "south", "南斗星名展示约定"),
    ("贪狼", 54061, "天枢 / α UMa", True, "north", "北斗传统别名"),
    ("巨门", 53910, "天璇 / β UMa", True, "north", "北斗传统别名"),
    ("天相", 90496, "斗宿二 / λ Sgr", True, "south", "南斗星名展示约定"),
    ("天梁", 93864, "斗宿五 / τ Sgr", True, "south", "南斗星名展示约定"),
    ("七杀", 89341, "斗宿三 / μ Sgr", True, "south", "南斗星名展示约定"),
    ("破军", 67301, "瑶光 / η UMa", True, "north", "北斗传统别名"),
    ("禄存", 58001, "天玑 / γ UMa", False, "north", "北斗传统别名"),
    ("文曲", 59774, "天权 / δ UMa", False, "north", "北斗传统别名"),
    ("左辅", 65477, "辅 / Alcor", False, "north", "辅星展示约定"),
)
MAJOR_ORDER = (
    "紫微",
    "天机",
    "太阳",
    "武曲",
    "天同",
    "廉贞",
    "天府",
    "太阴",
    "贪狼",
    "巨门",
    "天相",
    "天梁",
    "七杀",
    "破军",
)
EDGES = {
    "north": ((54061, 53910, 58001, 59774, 54061), (59774, 62956, 65378, 67301)),
    "south": ((89341, 90496, 92041, 92855, 93864, 93506, 92041),),
}
UNMAPPED = [
    {"names": ["文昌", "三台"], "reason": "存在同名多星星官，不能任取一颗代替斗数星曜"},
    {"names": ["右弼"], "reason": "隐元等说法没有在本预览中采用的唯一可核对 HIP 目标"},
    {
        "names": ["火星", "铃星", "擎羊", "陀罗"],
        "reason": "未确认斗数星曜到物理天体的唯一对应；不因同名把火星直接当作 Mars",
    },
    {
        "names": ["天魁", "天钺", "天马", "八座", "其他杂曜", "四化"],
        "reason": "尚无本预览采用的可靠单天体对应，不分配虚构坐标",
    },
]


def project_all_sky(altitude, azimuth):
    """单盘等距方位投影：天顶为圆心，地平线为半径的一半，天底在外缘。"""
    radius = (90 - altitude) / 180
    angle = math.radians(azimuth)
    return [-radius * math.sin(angle), -radius * math.cos(angle)]


def parse_preview_request(content):
    """本地接受完整 /星图 指令或同样的参数，四前缀仍共用原解析器。"""
    if isinstance(content, str):
        parts = content.split(maxsplit=1)
        if parts and parts[0].casefold() in {"/星图", "/xingtu", "/xt", "/star"}:
            content = parts[1] if len(parts) > 1 else ""
    request = parse_request(content)
    if request.action == "help":
        raise ValueError("预览请输入星图时间与地点；本脚本不处理帮助指令。")
    return request


def compute_ziwei(sky, content, settings=None, now=None):
    """沿用真实天球计算，过滤出明确列出的天体；命盘虚星不参与坐标计算。"""
    settings = settings or ChartSettings()
    now = now or datetime.now(timezone.utc)
    request = parse_preview_request(content)
    site, zone, source = resolve_place(
        sky.places, request.place_text or settings.default_place, settings.coordinate_timezone
    )
    zone = request.timezone_override or zone
    moment, note = resolve_time(request, zone, settings.default_time, now)
    # 此图以对象目录定义范围，不以普通星图的星等阈值隐藏选定对象。
    original = sky.compute(moment.isoformat(), site, zone, magnitude_limit=8)
    lookup = {
        star["hip"]: star for scene in original["hemispheres"].values() for star in scene["stars"]
    }
    missing = sorted({row[1] for row in CATALOG} - lookup.keys())
    if missing:
        raise ValueError(f"紫微预览所需的真实恒星坐标缺失：HIP {missing}")
    scenes = {
        hemisphere: {"objects": [], "constellations": []} for hemisphere in ("upper", "lower")
    }
    by_hip = {}
    for name, hip, astronomical_name, major, group, mapping in CATALOG:
        star = dict(lookup[hip])
        star.update(
            name=name,
            astronomical_name=astronomical_name,
            major=major,
            group=group,
            mapping=mapping,
            key=f"hip:{hip}",
            kind="star",
        )
        hemisphere = "upper" if star["altitude_deg"] >= 0 else "lower"
        scenes[hemisphere]["objects"].append(star)
        by_hip[hip] = star
    t = sky.core.ts.from_datetime(moment)
    observer = sky.core.earth + wgs84.latlon(
        site["latitude"], site["longitude"], elevation_m=site["elevation_m"]
    )
    try:
        here = observer.at(t)
        for name, key, naif in (("太阳", "sun", 10), ("太阴", "moon", 301)):
            alt, az, _ = here.observe(sky.core.kernel[naif]).apparent().altaz()
            a, z = float(alt.degrees), float(az.degrees)
            hemisphere = "upper" if a >= 0 else "lower"
            scenes[hemisphere]["objects"].append(
                {
                    "key": key,
                    "kind": key,
                    "name": name,
                    "major": True,
                    "astronomical_name": "太阳 / Sun" if key == "sun" else "月球 / Moon",
                    "naif_id": naif,
                    "target_kind": "body_center",
                    "group": "luminaries",
                    "mapping": "日月名称",
                    "magnitude": None,
                    "altitude_deg": a,
                    "azimuth_deg": z,
                    "xy": project(a, z, hemisphere),
                }
            )
    except EphemerisRangeError as exc:
        raise ValueError("日月计算触及历表边界，请选择稍远离边界的日期。") from exc
    for group, chains in EDGES.items():
        for hemisphere, scene in scenes.items():
            lines = []
            for chain in chains:
                for first, second in zip(chain, chain[1:]):
                    first, second = by_hip[first], by_hip[second]
                    arc = clipped_arc(
                        direction(first["altitude_deg"], first["azimuth_deg"]),
                        direction(second["altitude_deg"], second["azimuth_deg"]),
                        hemisphere,
                    )
                    if arc:
                        lines.append(arc)
            if lines:
                scene["constellations"].append({"group": group, "lines": lines})
    objects = [
        {
            **obj,
            "single_xy": project_all_sky(obj["altitude_deg"], obj["azimuth_deg"]),
            "display_state": "bright" if obj["altitude_deg"] >= 0 else "dim",
        }
        for scene in scenes.values()
        for obj in scene["objects"]
    ]
    return {
        **{
            key: original[key]
            for key in (
                "epoch_utc",
                "epoch_local",
                "site",
                "sun_altitude_deg",
                "sky_condition",
                "projection",
            )
        },
        "profile": PROFILE_VERSION,
        "hemispheres": scenes,
        "single_chart": {
            "objects": objects,
            "horizon_radius": 0.5,
            "projection": "full_sky_azimuthal_equidistant",
            "center": "zenith",
            "north": "up",
            "east": "left",
            "edge": "nadir_limit",
        },
        "time_note": note,
        "timezone": zone,
        "site_source": source,
        "unmapped": UNMAPPED,
        "notes": [
            "本地星名预览；位置来自真实站心天球，不是紫微斗数十二宫命盘。",
            "紫微采用现代北极星 HIP 11767 的展示约定；历史帝星说法不唯一。",
            "南斗、左辅采用文档列出的展示对应，不宣称唯一历史定论。",
            "只绘选定天体，不绘背景恒星及其他行星。",
            "明暗表示地平线上下的显示状态，不表示斗数庙旺，也不保证肉眼可见。",
            "单盘是天顶中心的全天投影；天底为外缘极限，不能按图面积比较半球大小。",
            "恒星点亮度按星表 V 星等；强调环和标签只表示主辅类别。",
            "日月星等未计算，符号只定位，不伪造亮度或当天月相。",
            "上下半球、折射、自行及实际可见性定义沿用普通星图。",
        ],
        "provenance": {
            **original["provenance"],
            "ziwei_profile": PROFILE_VERSION,
            "ziwei_sources": SOURCES,
            "ziwei_algorithm_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    }
