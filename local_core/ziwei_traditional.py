"""《全书》安星核心的独立研究对照；不改变正式指令或现有预览规则。"""

from .ziwei_palaces import BRANCHES, PALACES

STEMS = "甲乙丙丁戊己庚辛壬癸"
PROFILE = "quanshu-core-comparison-v1"
SOURCE = "https://zh.wikisource.org/w/index.php?oldid=1963110"
NAYIN = (
    "海中金",
    "炉中火",
    "大林木",
    "路旁土",
    "剑锋金",
    "山头火",
    "涧下水",
    "城头土",
    "白蜡金",
    "杨柳木",
    "泉中水",
    "屋上土",
    "霹雳火",
    "松柏木",
    "长流水",
    "沙中金",
    "山下火",
    "平地木",
    "壁上土",
    "金箔金",
    "覆灯火",
    "天河水",
    "大驿土",
    "钗钏金",
    "桑柘木",
    "大溪水",
    "沙中土",
    "天上火",
    "石榴木",
    "大海水",
)
BUREAU = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
ZIWEI_OFFSETS = {"紫微": 0, "天机": -1, "太阳": -3, "武曲": -4, "天同": -5, "廉贞": -8}
TIANFU_OFFSETS = {
    "天府": 0,
    "太阴": 1,
    "贪狼": 2,
    "巨门": 3,
    "天相": 4,
    "天梁": 5,
    "七杀": 6,
    "破军": 10,
}
FOUR_HUA = (
    ("廉贞", "破军", "武曲", "太阳"),
    ("天机", "天梁", "紫微", "太阴"),
    ("天同", "天机", "文昌", "廉贞"),
    ("太阴", "天同", "天机", "巨门"),
    ("贪狼", "太阴", "右弼", "天机"),
    ("武曲", "贪狼", "天梁", "文曲"),
    ("太阳", "武曲", "太阴", "天同"),
    ("巨门", "太阳", "文曲", "文昌"),
    ("天梁", "紫微", "天府", "武曲"),
    ("破军", "巨门", "太阴", "贪狼"),
)


def palace_stems(year_stem):
    first = (2 * (year_stem % 5 + 1)) % 10
    return {BRANCHES[b]: STEMS[(first + (b - 2) % 12) % 10] for b in range(12)}


def five_elements(stem, branch):
    index = next(i for i in range(60) if STEMS[i % 10] == stem and BRANCHES[i % 12] == branch)
    nayin = NAYIN[index // 2]
    return {
        "stem_branch": stem + branch,
        "nayin": nayin,
        "element": nayin[-1],
        "number": BUREAU[nayin[-1]],
    }


def ziwei_start(day, bureau):
    if not 1 <= day <= 30 or bureau not in BUREAU.values():
        raise ValueError("安紫微须使用农历初一至三十及二至六局。")
    quotient = (day + bureau - 1) // bureau
    padding = quotient * bureau - day
    shift = padding if padding % 2 == 0 else -padding
    return (2 + quotient - 1 + shift) % 12


def traditional_core(assignment, leap_policy="quanshu_next"):
    if not assignment["available"]:
        raise ValueError(assignment["reason"])
    if leap_policy not in {"quanshu_next", "preview_split"}:
        raise ValueError("未知闰月研究版本。")
    lunar = assignment["lunar"]
    month = lunar["month"]
    if lunar["leap"]:
        if month == 12:
            raise ValueError("闰十二月跨年解释未冻结，不自动猜测。")
        month += int(leap_policy == "quanshu_next" or lunar["day"] > 15)
    hour = BRANCHES.index(assignment["hour_branch"])
    year_stem, year_branch = (lunar["year"] - 4) % 10, (lunar["year"] - 4) % 12
    life, body = (month + 1 - hour) % 12, (month + 1 + hour) % 12
    names = {branch: PALACES[(life - b) % 12] for b, branch in enumerate(BRANCHES)}
    stems = palace_stems(year_stem)
    bureau = five_elements(stems[BRANCHES[life]], BRANCHES[life])
    ziwei = ziwei_start(lunar["day"], bureau["number"])
    tianfu = (4 - ziwei) % 12
    positions = {name: (ziwei + delta) % 12 for name, delta in ZIWEI_OFFSETS.items()}
    positions.update({name: (tianfu + delta) % 12 for name, delta in TIANFU_OFFSETS.items()})
    lu = (2, 3, 5, 6, 5, 6, 8, 9, 11, 0)[year_stem]
    if year_branch in (2, 6, 10):
        fire, bell = 1, 3
    elif year_branch in (0, 4, 8):
        fire, bell = 2, 10
    elif year_branch in (1, 5, 9):
        fire, bell = 3, 10
    else:
        fire, bell = 9, 10
    positions.update(
        {
            "禄存": lu,
            "文昌": (10 - hour) % 12,
            "文曲": (4 + hour) % 12,
            "左辅": (month + 3) % 12,
            "右弼": (11 - month) % 12,
            "擎羊": (lu + 1) % 12,
            "陀罗": (lu - 1) % 12,
            "火星": (fire + hour) % 12,
            "铃星": (bell + hour) % 12,
            "地空": (11 - hour) % 12,
            "地劫": (11 + hour) % 12,
        }
    )
    return {
        "profile": PROFILE,
        "source": SOURCE,
        "lunar": lunar,
        "effective_month": month,
        "hour_branch": BRANCHES[hour],
        "year_stem_branch": STEMS[year_stem] + BRANCHES[year_branch],
        "life_branch": BRANCHES[life],
        "body_branch": BRANCHES[body],
        "palace_stems": stems,
        "palace_names": names,
        "bureau": bureau,
        "ziwei_branch": BRANCHES[ziwei],
        "tianfu_branch": BRANCHES[tianfu],
        "positions": {
            name: {"branch": BRANCHES[b], "palace": names[BRANCHES[b]]}
            for name, b in positions.items()
        },
        "four_hua": {hua: name for hua, name in zip(("禄", "权", "科", "忌"), FOUR_HUA[year_stem])},
        "calendar_contract": {
            "basis": "沿用当前预览的当地民用日期转中国农历，23点换次日；不做真太阳时",
            "leap_policy": leap_policy,
            "sex": "仅静态安星；不计算需要性别的运限和十二长生",
            "fire_bell": "卷二年支定位，依现代安星文档补全子时起位并顺数生时",
            "four_hua": "采用上述固定全书录文；壬科天府与通行壬科左辅有别",
        },
    }


def compare_sky(data, leap_policy="quanshu_next"):
    traditional = traditional_core(data["palace_layer"]["assignment"], leap_policy)
    rows = []
    for obj in data["single_chart"]["objects"]:
        symbolic = traditional["positions"][obj["name"]]
        branch = obj["research_branch"]
        rows.append(
            {
                "key": obj["key"],
                "name": obj["name"],
                "major": obj["major"],
                "traditional_branch": symbolic["branch"],
                "traditional_palace": symbolic["palace"],
                "real_research_branch": branch,
                "real_research_palace": traditional["palace_names"][branch],
                "preview_palace_name": obj["research_palace"],
                "same_branch": branch == symbolic["branch"],
                "real_target": obj["astronomical_name"]
                if obj["kind"] == "star"
                else {"sun": "太阳", "moon": "月球"}[obj["kind"]],
                "mapping": obj.get("mapping", "日月实体"),
                "hip": obj.get("hip"),
                "naif_id": obj.get("naif_id"),
                "ra_date_deg": obj["ra_date_deg"],
                "dec_date_deg": obj["dec_date_deg"],
                "altitude_deg": obj["altitude_deg"],
                "azimuth_deg": obj["azimuth_deg"],
                "magnitude": obj["magnitude"],
            }
        )
    return {
        "traditional": traditional,
        "rows": rows,
        "matching_names": [r["name"] for r in rows if r["same_branch"]],
        "interpretation": "地支同格仅在当前别名映射及研究宫界假设下成立；不是物理角差或正确率",
    }
