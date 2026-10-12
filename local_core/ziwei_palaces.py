"""古籍宿度的今星锚定研究层，以及按当地民用时间安命的十二事项宫。"""

import hashlib
import math
from datetime import datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import numpy as np
from lunar_python import Solar
from skyfield.api import Star

BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
PALACES = (
    "命宫",
    "兄弟",
    "夫妻",
    "子女",
    "财帛",
    "疾厄",
    "迁移",
    "交友",
    "官禄",
    "田宅",
    "福德",
    "父母",
)
PROFILE = "jinshu-current-anchor-equatorial-v1"
SOURCE = "https://zh.wikisource.org/zh/晉書/卷011"
# 地支、十二次、入次宿名、主文古度、当前该宿第一星的 HIP。
STARTS = (
    ("子", "玄枵", "女", 8, 102618),
    ("丑", "星纪", "斗", 12, 92041),
    ("寅", "析木", "尾", 10, 82514),
    ("卯", "大火", "氐", 5, 72622),
    ("辰", "寿星", "轸", 12, 59803),
    ("巳", "鹑尾", "张", 17, 48356),
    ("午", "鹑火", "柳", 9, 42313),
    ("未", "鹑首", "井", 16, 30343),
    ("申", "实沈", "毕", 12, 20889),
    ("酉", "大梁", "胃", 7, 12719),
    ("戌", "降娄", "奎", 5, 4463),
    ("亥", "娵訾", "危", 16, 109074),
)


def assign_palaces(epoch_local):
    """寅起正月，顺月逆时安命；民用时、晚子换日、闰月十五日分界。"""
    civil = datetime.fromisoformat(epoch_local)
    if not 1900 <= civil.year <= 2100:
        return {"available": False, "reason": "本地安命历法验收范围为 1900–2100 年"}
    adjusted = civil + timedelta(days=1) if civil.hour == 23 else civil
    lunar = Solar.fromYmdHms(
        adjusted.year, adjusted.month, adjusted.day, adjusted.hour, adjusted.minute, adjusted.second
    ).getLunar()
    leap = lunar.getMonth() < 0
    month = min(12, abs(lunar.getMonth()) + int(leap and lunar.getDay() > 15))
    hour = (civil.hour + 1) // 2 % 12
    life = (2 + month - 1 - hour) % 12
    body = (2 + month - 1 + hour) % 12
    return {
        "available": True,
        "civil": civil.isoformat(),
        "astrology_date": adjusted.isoformat(),
        "lunar": {
            "year": lunar.getYear(),
            "month": abs(lunar.getMonth()),
            "day": lunar.getDay(),
            "leap": leap,
        },
        "effective_month": month,
        "hour_branch": BRANCHES[hour],
        "life_branch": BRANCHES[life],
        "body_branch": BRANCHES[body],
        "names": {branch: PALACES[(life - index) % 12] for index, branch in enumerate(BRANCHES)},
        "malefics": assign_malefics(lunar.getYear(), hour),
        "rules": {
            "source": "https://zh.wikisource.org/zh/紫微斗數全書/卷二",
            "time": "地点民用钟表时间，不做真太阳时校正",
            "lunar_date": "地点民用日期套中国农历",
            "late_zi": "23点的子时按下一民用日期换算农历",
            "leap_month": "前十五日取本月，之后取次月；十二月封顶",
            "fire_bell": "按年支起子位，火铃均顺数至生时",
        },
        "lunar_python": version("lunar-python"),
    }


def assign_malefics(lunar_year, hour_index):
    """零基地支；年干安禄存，羊陀夹禄，火铃顺时，亥起子顺劫逆空。"""
    stem = (lunar_year - 4) % 10
    year_branch = (lunar_year - 4) % 12
    lu = (2, 3, 5, 6, 5, 6, 8, 9, 11, 0)[stem]
    fire, bell = {0: (2, 10), 1: (3, 10), 2: (1, 3), 3: (9, 10)}[year_branch % 4]
    positions = (
        ("擎羊", lu + 1),
        ("陀罗", lu - 1),
        ("火星", fire + hour_index),
        ("铃星", bell + hour_index),
        ("地空", 11 - hour_index),
        ("地劫", 11 + hour_index),
    )
    return [
        {
            "name": name,
            "branch": BRANCHES[index % 12],
            "kind": "symbolic",
            "key": f"sha:{name}",
            "hip": None,
            "naif_id": None,
            "magnitude": None,
            "scope": "斗数安星符号，无实体天文坐标或视星等",
        }
        for name, index in positions
    ]


def equatorial_to_horizon(ra_deg, dec_deg, latitude, sidereal_deg):
    """日期真赤道/真春分点方向转当地地平，无折射；角度单位为现代度。"""
    phi, dec = math.radians(latitude), math.radians(dec_deg)
    hour = math.radians(sidereal_deg - ra_deg)
    east = -math.cos(dec) * math.sin(hour)
    north = math.cos(phi) * math.sin(dec) - math.sin(phi) * math.cos(dec) * math.cos(hour)
    up = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(hour)
    return math.degrees(math.asin(max(-1, min(1, up)))), math.degrees(math.atan2(east, north)) % 360


def build_palace_layer(sky, here, t, site, epoch_local, project):
    assignment = assign_palaces(epoch_local)
    sidereal = float(t.gast) * 15 + site["longitude"]
    boundaries = []
    for branch, ci, lodge, du, hip in STARTS:
        if hip not in sky.indices:
            raise ValueError(f"宫界候选距星缺失：HIP {hip}")
        row = sky.rows[sky.indices[hip]]
        star = Star(
            ra_hours=row[2],
            dec_degrees=row[3],
            parallax_mas=row[4],
            ra_mas_per_year=row[5],
            dec_mas_per_year=row[6],
            epoch=sky.core.ts.J(1991.25),
        )
        ra, _, _ = here.observe(star).apparent().radec(epoch="date")
        start = (float(ra.hours) * 15 + du * 360 / 365.25) % 360
        boundaries.append(
            {
                "branch": branch,
                "ci": ci,
                "lodge": lodge,
                "ancient_du": du,
                "anchor_hip": hip,
                "anchor_ra_deg": float(ra.hours) * 15,
                "start_ra_deg": start,
            }
        )
    boundaries.sort(key=lambda item: item["start_ra_deg"])
    expected = "戌酉申未午巳辰卯寅丑子亥"
    if "".join(b["branch"] for b in boundaries) != expected:
        raise ValueError("今星锚定宫界次序与本地研究模型不符，拒绝生成错序宫界。")
    for index, item in enumerate(boundaries):
        end = boundaries[(index + 1) % 12]["start_ra_deg"]
        span = (end - item["start_ra_deg"]) % 360
        item["span_deg"] = span
        item["end_ra_deg"] = end
        center = (item["start_ra_deg"] + span / 2) % 360
        alt, az = equatorial_to_horizon(center, 0, site["latitude"], sidereal)
        item["label_xy"] = project(alt, az)
        item["name"] = assignment.get("names", {}).get(item["branch"], item["ci"])
        item["body"] = assignment.get("body_branch") == item["branch"]
        curves, current = [], []
        for dec in np.linspace(-89.99, 89.99, 241):
            alt, az = equatorial_to_horizon(
                item["start_ra_deg"], float(dec), site["latitude"], sidereal
            )
            xy = project(alt, az)
            if current and math.dist(current[-1], xy) > 0.15:
                if len(current) > 1:
                    curves.append(current)
                current = []
            current.append(xy)
        if len(current) > 1:
            curves.append(current)
        item["curves"] = curves
    symbols = []
    for item in assignment.get("malefics", []):
        sector = next(s for s in boundaries if s["branch"] == item["branch"])
        center = (sector["start_ra_deg"] + sector["span_deg"] / 2) % 360
        options = []
        for dec in (25, -25, 45, -45, 65, -65, 80, -80, 10, -10):
            alt, az = equatorial_to_horizon(center, dec, site["latitude"], sidereal)
            options.append(project(alt, az))
        symbols.append({**item, "palace": sector["name"], "layout_options": options})
    return {
        "profile": PROFILE,
        "status": "research_current_anchor_not_historical_recovery",
        "source": SOURCE,
        "projection_context": {"latitude_deg": site["latitude"], "sidereal_deg": sidereal},
        "symbolic_malefics": symbols,
        "assignment": assignment,
        "sectors": boundaries,
        "basis": "日期真赤道宿度经线；当前第一宿星作为候选距星",
        "ancient_circle_du": 365.25,
        "offset_convention": "将主文数字解释为从候选距星起的古度偏移",
        "uncertainty": "古历元、古距星及初度起算未定；此为今星锚定示意，未认证真实古宫界",
        "label_basis": "每区赤道中点为文字引线锚，不是物理星体或天空面积中心",
        "algorithm_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def project_north_pole(ra_deg, dec_deg):
    """北天极中心全天等距投影；日期真赤经 0h 在上、6h 在左。"""
    radius = (90 - dec_deg) / 180
    angle = math.radians(ra_deg)
    return [-radius * math.sin(angle), -radius * math.cos(angle)]


def locate_sector(ra_deg, sectors):
    for sector in sectors:
        if (ra_deg - sector["start_ra_deg"]) % 360 < sector["span_deg"]:
            return sector
    raise ValueError("天体方向无法分配到古界研究区域。")
