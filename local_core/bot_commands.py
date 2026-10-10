"""星图指令的输入约定；不依赖 AstrBot，不保存用户时间或地点。"""

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from .geography import normalize
from .sky_chart import validate_site
from .time_input import PRECISION_LABELS, localize, parse_timezone

COMPACT_LENGTHS = {4: 1, 6: 2, 8: 3, 10: 4, 12: 5, 14: 6}
DATE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
CLOCK = re.compile(r"^(\d{2})(?::(\d{2})(?::(\d{2}))?)?$")
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
COORDINATE = re.compile(rf"^([NSEW])?({NUMBER})(?:°|度)?([NSEW])?$", re.IGNORECASE)
ACTIONS = {"帮助": "help", "时间": "time", "地点": "place", "时地": "at"}
DEFAULT_TIME = "08:00:00"


def migrate_default_time(config):
    """一次性迁移旧版出厂的 12 点值，其他自定义值保留。"""
    revision = config.get("_input_defaults_version", 0)
    if isinstance(revision, int) and revision >= 1:
        return
    if config.get("default_time", DEFAULT_TIME) == "12:00:00":
        config["default_time"] = DEFAULT_TIME
    config["_input_defaults_version"] = 1
    save = getattr(config, "save_config", None)
    if callable(save):
        save()


@dataclass(frozen=True)
class ChartSettings:
    default_place: str = "北京"
    default_time: str = DEFAULT_TIME
    coordinate_timezone: str = "Asia/Shanghai"
    magnitude_limit: float = 6
    lines: bool = True
    names: bool = True
    constellation_names: bool = True

    @classmethod
    def from_mapping(cls, config):
        result = cls(
            default_place=str(config.get("default_place", "北京")).strip(),
            default_time=str(config.get("default_time", DEFAULT_TIME)).strip(),
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
        raise ValueError("默认时间配置须为 HH:MM:SS，例如 08:00:00。")
    try:
        return datetime.strptime(value, "%H:%M:%S").time()
    except ValueError as exc:
        raise ValueError("默认时间配置的时、分、秒超出范围。") from exc


def validate_time_text(value):
    date, separator, clock = value.replace("T", " ").partition(" ")
    if date.isascii() and date.isdigit():
        length = COMPACT_LENGTHS.get(len(date))
        if length is None or (separator and length > 3):
            raise ValueError("紧凑日期须为 4/6/8/10/12/14 位，至少提供四位年份。")
        parts = [date[:4]] + [date[i : i + 2] for i in range(4, len(date), 2)]
        parts += [None] * (6 - length)
    else:
        match = DATE.fullmatch(date)
        if not match:
            raise ValueError("至少提供四位年份；支持 YYYYMMDDHHMMSS 或 YYYY-MM-DD HH:MM:SS。")
        parts = [*match.groups(), None, None, None]
    if separator:
        match = CLOCK.fullmatch(clock)
        if not match:
            raise ValueError("时分秒格式须为 HH、HH:MM 或 HH:MM:SS。")
        parts[3:] = match.groups()
    try:
        datetime(
            int(parts[0]),
            int(parts[1] or 1),
            int(parts[2] or 1),
            *(int(part or 0) for part in parts[3:]),
        )
    except ValueError as exc:
        raise ValueError("日期或时分秒无效；当前不接受闰秒 60。") from exc
    return tuple(parts)


def parse_coordinates(text):
    text = unicodedata.normalize("NFKC", text.replace("º", "°")).replace("−", "-")
    text = re.sub(r"\s*(°|度)\s*", r"\1", text)
    prefix_style = bool(re.match(rf"^[NSEW]\s*{NUMBER}", text, re.I))
    if prefix_style:
        text = re.sub(r"(?<![\d°])\b([NSEW])\s+(?=[+\-\d.])", r"\1", text, flags=re.I)
    text = re.sub(r"(?<=[\d°])\s+([NSEW])\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![\d°])\b([NSEW])\s+(?=[+\-\d.])", r"\1", text, flags=re.IGNORECASE)
    tokens = re.split(r"[\s,;]+", text)
    if len(tokens) != 2:
        return None
    matches = [COORDINATE.fullmatch(token) for token in tokens]
    if not all(matches):
        return None
    values = []
    for match in matches:
        first, number, last = match.groups()
        if first and last and first.upper() != last.upper():
            raise ValueError("同一个坐标的方向标记不一致。")
        direction = (first or last or "").upper()
        value = float(number)
        if value < 0 and direction in {"N", "E"}:
            raise ValueError("负数坐标与 N/E 方向冲突。")
        if direction in {"S", "W"}:
            value = -abs(value)
        values.append((direction, value))
    if any(direction for direction, _ in values):
        axes = {
            "latitude" if direction in {"N", "S"} else "longitude": value
            for direction, value in values
            if direction
        }
        if not all(direction for direction, _ in values) or len(axes) != 2:
            raise ValueError("经纬度须分别提供一个 N/S 纬度和一个 E/W 经度。")
    else:
        axes = {"latitude": values[0][1], "longitude": values[1][1]}
    return validate_site({**axes, "label": "经纬度定位"})


def extract_arguments(tokens):
    time_text, remaining = None, []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        candidate = (token.isascii() and token.isdigit() and len(token) >= 4) or bool(
            re.match(r"^\d{4}[-T]", token)
        )
        if candidate:
            if time_text is not None:
                raise ValueError("只支持一个日期时间参数。")
            time_text = token
            coordinate_pair_follows = (
                index + 2 < len(tokens)
                and re.fullmatch(NUMBER, tokens[index + 1])
                and re.fullmatch(NUMBER, tokens[index + 2])
            )
            if (
                index + 1 < len(tokens)
                and not coordinate_pair_follows
                and CLOCK.fullmatch(tokens[index + 1])
                and len(token) <= 10
                and "T" not in token
            ):
                time_text += " " + tokens[index + 1]
                index += 1
            validate_time_text(time_text)
        else:
            remaining.append(token)
        index += 1
    place = " ".join(remaining) or None
    if place:
        if len(place) > 80:
            raise ValueError("地点参数须为不超过 80 字的文本。")
        coordinates = parse_coordinates(place)
        if coordinates is None and ("°" in place or re.fullmatch(rf"{NUMBER}[NSEW]", place, re.I)):
            raise ValueError("经纬度须输入完整的一对，例如 30.25°N 120.5°E。")
        if coordinates is None and not re.search(r"[^\d\s:.,;+\-°]", place):
            raise ValueError("日期时间至少需要四位年份；经纬度须输入完整的一对。")
    return time_text, place


def parse_request(content):
    if not isinstance(content, str) or len(content) > 300:
        raise ValueError("星图指令参数须为不超过 300 字的文本。")
    text = unicodedata.normalize("NFKC", content.replace("º", "°")).replace("−", "-")
    text = " ".join(text.split())
    if not text:
        return ChartRequest()
    action, _, rest = text.partition(" ")
    action = ACTIONS.get(action.casefold(), action.casefold())
    if action == "help":
        if rest:
            raise ValueError("帮助指令不接受其他参数，请使用 /星图 help。")
        return ChartRequest(action="help")
    explicit = action if action in {"time", "place", "at"} else None
    if explicit is None:
        rest = text
    zone = None
    tokens = rest.split()
    if tokens and tokens[-1].startswith("tz="):
        zone = tokens.pop()[3:]
        parse_timezone(zone)
        rest = " ".join(tokens)
    if any(token.startswith("tz=") for token in tokens):
        raise ValueError("时区参数 tz=... 须放在指令末尾。")
    time_text, place = extract_arguments(rest.split())
    if explicit == "time" and (time_text is None or place is not None):
        raise ValueError("时间指令示例：/星图 time 20250102；地点组合可直接输入 北京 20250102。")
    if explicit == "place" and (place is None or time_text is not None):
        raise ValueError("地点指令示例：/星图 place 北京；地点组合可直接输入 北京 20250102。")
    if explicit == "at" and (time_text is None or place is None):
        raise ValueError("时地指令示例：/星图 at 北京 20250102。")
    action = "at" if time_text and place else "time" if time_text else "place" if place else "now"
    return ChartRequest(action, time_text, place, zone)


def resolve_place(places, query, coordinate_timezone):
    """只采用确定的地点；同名候选用 GeoNames ID 明确选择。"""
    site = parse_coordinates(query)
    if site:
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
    precision = (
        "second"
        if second
        else "minute"
        if minute
        else "hour"
        if hour
        else "day"
        if day
        else "month"
        if month
        else "year"
    )
    naive = datetime(
        int(year),
        int(month or 1),
        int(day or 1),
        clock.hour if hour is None else int(hour),
        clock.minute if minute is None else int(minute),
        clock.second if second is None else int(second),
    )
    moment = localize(naive, zone).astimezone(timezone.utc)
    note = f"输入到{dict(PRECISION_LABELS, year='年', month='月')[precision]}"
    if month is None:
        note += "；缺月补 1 月"
    if day is None:
        note += "；缺日补 1 号"
    if precision != "second":
        note += f"；缺失时分秒按配置 {configured_time} 补齐"
    return moment, note


def help_text(settings):
    return (
        "星图\n"
        f"/星图 — 当前时刻，默认地点：{settings.default_place}\n"
        "/星图 help（帮助）\n"
        "/星图 200010100100 — 2000-10-10 01:00:00，默认地点\n"
        "/星图 20010101 — 2001-01-01，补齐默认时间\n"
        "/星图 2025 或 202501 — 缺月补 1 月，缺日补 1 号\n"
        "/星图 北京 — 当前北京\n"
        "/星图 北京 20250102 — 指定地点和日期，顺序也可交换\n"
        "/星图 30.25°N 120.5°E [20250102] — 经纬度，可追加时间\n"
        "/星图 30.25,120.5 — 也支持 纬度,经度 或两个小数\n"
        "四个前缀 /星图、/xingtu、/xt、/star 完全等效。\n"
        "公历紧凑时间：YYYY、YYYYMM、YYYYMMDD、YYYYMMDDHH、YYYYMMDDHHMM、"
        "YYYYMMDDHHMMSS；也支持 YYYY-MM-DD HH:MM:SS。至少提供年份。\n"
        f"每次一张双半球图，缺少的时分秒按配置 {settings.default_time} 补齐。\n"
        "指定时间按所选地点的时区解释，可在末尾加 tz=UTC+08:00 等显式时区。\n"
        f"经纬度默认时区 {settings.coordinate_timezone}；N/S 为纬度，E/W 为经度。\n"
        "同名地点按提示使用 #编号，例如 /star place #5128581。\n"
        "旧入口 time/时间、place/地点、at/时地仍兼容。\n"
        "上半球为地平线以上；暗面为地球遮挡方向。"
        "星等映射亮度，日光、天气和地形会影响实际可见性。"
    )
