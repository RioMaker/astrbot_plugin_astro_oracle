"""星图指令的输入约定；不依赖 AstrBot，不保存用户时间或地点。"""

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .geography import normalize
from .sky_chart import validate_site
from .time_input import PATTERN, PRECISION_LABELS, localize, parse_timezone

DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}(?::\d{2}(?::\d{2})?)?)?)(?:\s+(.+))?$")
COORDINATES = re.compile(r"^([+-]?\d+(?:\.\d+)?)[,，]([+-]?\d+(?:\.\d+)?)$")
ACTIONS = {"帮助": "help", "时间": "time", "地点": "place", "时地": "at"}


@dataclass(frozen=True)
class ChartSettings:
    default_place: str = "北京"
    default_time: str = "12:00:00"
    coordinate_timezone: str = "Asia/Shanghai"
    magnitude_limit: float = 6
    lines: bool = True
    names: bool = True
    constellation_names: bool = True

    @classmethod
    def from_mapping(cls, config):
        result = cls(
            default_place=str(config.get("default_place", "北京")).strip(),
            default_time=str(config.get("default_time", "12:00:00")).strip(),
            coordinate_timezone=str(config.get("coordinate_timezone", "Asia/Shanghai")).strip(),
            magnitude_limit=config.get("magnitude_limit", 6),
            lines=config.get("show_constellation_lines", True),
            names=config.get("show_star_names", True),
            constellation_names=config.get("show_constellation_names", True),
        )
        default_clock(result.default_time)
        parse_timezone(result.coordinate_timezone)
        if not 1 <= len(result.default_place) <= 80:
            raise ValueError("请在 AstrBot 配置中填写 1–80 字的默认地点。")
        value = result.magnitude_limit
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not -2 <= value <= 8
        ):
            raise ValueError("AstrBot 配置中的恒星星等上限须为 -2 至 8 的数值。")
        for value in (result.lines, result.names, result.constellation_names):
            if not isinstance(value, bool):
                raise ValueError("AstrBot 配置中的名称和连线开关须为布尔值。")
        return result


@dataclass(frozen=True)
class ChartRequest:
    action: str = "now"
    time_text: str | None = None
    place_text: str | None = None
    timezone_override: str | None = None


def default_clock(value):
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", value):
        raise ValueError("默认时间配置须为 HH:MM:SS，例如 12:00:00。")
    try:
        return datetime.strptime(value, "%H:%M:%S").time()
    except ValueError as exc:
        raise ValueError("默认时间配置的时、分、秒超出范围。") from exc


def validate_time_text(value):
    match = PATTERN.fullmatch(value)
    if not match:
        raise ValueError("时间格式：YYYY-MM-DD [HH[:MM[:SS]]]，使用公历。")
    try:
        datetime(*(int(part or 0) for part in match.groups()))
    except ValueError as exc:
        raise ValueError("日期或时分秒无效；当前不接受闰秒 60。") from exc
    return match.groups()


def parse_request(content):
    if not isinstance(content, str) or len(content) > 300:
        raise ValueError("星图指令参数须为不超过 300 字的文本。")
    text = " ".join(content.split())
    if not text:
        return ChartRequest()
    action, _, rest = text.partition(" ")
    action = ACTIONS.get(action.casefold(), action.casefold())
    if action == "help":
        if rest:
            raise ValueError("帮助指令不接受其他参数，请使用 /星图 help。")
        return ChartRequest(action="help")
    if action not in {"time", "place", "at"}:
        raise ValueError("子指令：help/帮助、time/时间、place/地点、at/时地。")
    zone = None
    tokens = rest.split()
    if tokens and tokens[-1].startswith("tz="):
        zone = tokens.pop()[3:]
        parse_timezone(zone)
        rest = " ".join(tokens)
    if action == "time":
        validate_time_text(rest)
        return ChartRequest(action=action, time_text=rest, timezone_override=zone)
    if action == "place":
        if not 1 <= len(rest) <= 80:
            raise ValueError("地点格式：/星图 place 北京，或 place 纬度,经度。")
        return ChartRequest(action=action, place_text=rest, timezone_override=zone)
    match = DATE_PREFIX.fullmatch(rest)
    if not match or not match[2] or len(match[2]) > 80:
        raise ValueError("时地格式：/星图 at 2026-10-10 20:30:00 北京。")
    validate_time_text(match[1])
    return ChartRequest(
        action=action, time_text=match[1], place_text=match[2], timezone_override=zone
    )


def resolve_place(places, query, coordinate_timezone):
    """只采用确定的地点；同名候选用 GeoNames ID 明确选择。"""
    match = COORDINATES.fullmatch(query)
    if match:
        site = validate_site(
            {"latitude": float(match[1]), "longitude": float(match[2]), "label": "经纬度定位"}
        )
        return site, coordinate_timezone, {"source": "用户指定经纬度"}
    identifier = re.fullmatch(r"#(\d+)", query)
    country = None
    if not identifier:
        country_match = re.fullmatch(r"(.+)[,，]([A-Za-z]{2})", query)
        if country_match:
            query, country = country_match[1].strip(), country_match[2].upper()
    key = normalize(query)
    exact, partial = [], []
    for row, names in zip(places.rows, places.keys):
        if country and row[6] != country:
            continue
        if identifier:
            if row[0] == int(identifier[1]):
                exact.append(row)
            continue
        if key not in names:
            continue
        partial.append(row)
        if key in [normalize(name) for name in (row[1], row[2], *row[3].split(","))]:
            exact.append(row)
    matches = exact or partial
    if not matches:
        raise ValueError("地点未找到，请输入城市/乡镇名、#GeoNames编号，或 纬度,经度。")
    if len(matches) != 1:
        matches.sort(key=lambda row: -row[8])
        candidates = "\n".join(f"#{r[0]} {r[1]} ({r[6]})" for r in matches[:5])
        raise ValueError("地点有多个匹配，请用下列编号替换地点参数：\n" + candidates)
    row = matches[0]
    site = validate_site(
        {
            "latitude": row[4],
            "longitude": row[5],
            "label": row[1] if identifier else query,
        }
    )
    return site, row[7], {"source": "GeoNames cities1000", "id": row[0], "country": row[6]}


def resolve_time(request, zone_name, configured_time, now):
    zone = parse_timezone(request.timezone_override or zone_name)
    if request.time_text is None:
        return now.astimezone(timezone.utc).replace(microsecond=0), "当前时刻（接收指令时）"
    year, month, day, hour, minute, second = validate_time_text(request.time_text)
    clock = default_clock(configured_time)
    precision = "second" if second else "minute" if minute else "hour" if hour else "day"
    naive = datetime(
        int(year),
        int(month),
        int(day),
        clock.hour if hour is None else int(hour),
        clock.minute if minute is None else int(minute),
        clock.second if second is None else int(second),
    )
    moment = localize(naive, zone).astimezone(timezone.utc)
    note = f"输入到{PRECISION_LABELS[precision]}"
    if precision != "second":
        note += f"；缺失时分秒按配置 {configured_time} 补齐"
    return moment, note


def help_text(settings):
    return (
        "星图\n"
        f"/星图 — 当前时刻，默认地点：{settings.default_place}\n"
        "/星图 help（帮助）\n"
        "/星图 time 2026-10-10 20:30:00（时间）\n"
        "/星图 place 上海（地点，使用当前时刻）\n"
        "/星图 at 2026-10-10 20:30:00 上海（时地）\n"
        "四个前缀 /星图、/xingtu、/xt、/star 完全等效。\n"
        "日期格式：公历 YYYY-MM-DD，可追加 HH、HH:MM、HH:MM:SS。\n"
        f"每次一张双半球图，缺少的时分秒按配置 {settings.default_time} 补齐。\n"
        "指定时间按所选地点的时区解释，可在末尾加 tz=UTC+08:00 等显式时区。\n"
        f"坐标示例：/xt place 39.9075,116.39723（默认 {settings.coordinate_timezone}）。\n"
        "同名地点按提示使用 #编号，例如 /star place #5128581。\n"
        "上半球为地平线以上；暗面为地球遮挡方向。"
        "星等映射亮度，日光、天气和地形会影响实际可见性。"
    )
