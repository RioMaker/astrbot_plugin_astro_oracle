"""保留输入的时间分辨率，避免把缺失的时分秒当成已知。"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[ T](\d{2})(?::(\d{2})(?::(\d{2}))?)?)?$"
)
RESOLUTIONS = {"day": 86400, "hour": 3600, "minute": 60, "second": 1}
PRECISION_LABELS = {"day": "日", "hour": "时", "minute": "分", "second": "秒"}


def parse_timezone(value: str) -> tzinfo:
    """支持 IANA 时区或显式 UTC 偏移；不依赖本机默认时区。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("请指定时区，例如 Asia/Shanghai、UTC 或 UTC+08:00。")
    value = value.strip()
    if value.upper() in {"UTC", "Z"}:
        return UTC
    match = re.fullmatch(r"(?:UTC)?([+-])(\d{2}):(\d{2})", value, re.IGNORECASE)
    if match:
        sign, hours, minutes = match.groups()
        hours, minutes = int(hours), int(minutes)
        if minutes > 59 or hours > 14 or (hours == 14 and minutes):
            raise ValueError("显式 UTC 偏移须在 -14:00 至 +14:00 之间。")
        offset = timedelta(hours=hours, minutes=minutes)
        return timezone(offset if sign == "+" else -offset)
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("未知时区，请使用 IANA 名称或 UTC±HH:MM。") from exc


def localize(naive: datetime, zone: tzinfo) -> datetime:
    """拒绝夏令时跳变导致的不存在或重叠时刻，要求显式偏移。"""
    candidates = {}
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        universal = candidate.astimezone(UTC)
        if universal.astimezone(zone).replace(tzinfo=None) == naive:
            candidates[universal] = candidate
    if not candidates:
        raise ValueError("该本地时刻因时区跳变不存在，请确认日期或使用显式 UTC 偏移。")
    if len(candidates) > 1:
        raise ValueError("该本地时刻因时区跳变出现两次，请用显式 UTC 偏移消除歧义。")
    return next(iter(candidates.values()))


@dataclass(frozen=True)
class TimeWindow:
    original: str
    timezone_name: str
    zone: tzinfo
    precision: str
    start: datetime
    end: datetime

    @property
    def is_instant(self) -> bool:
        return self.precision == "second"

    def samples(self, count: int = 7) -> list[datetime]:
        if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 25:
            raise ValueError("时间段采样数量须为 2–25 的整数。")
        if self.is_instant:
            return [self.start]
        duration = int((self.end - self.start).total_seconds())
        offsets = sorted(
            {min(round(index * duration / (count - 1)), duration - 1) for index in range(count)}
        )
        return [self.start + timedelta(seconds=offset) for offset in offsets]

    def as_dict(self) -> dict:
        return {
            "original": self.original,
            "timezone": self.timezone_name,
            "precision": self.precision,
            "precision_label": PRECISION_LABELS[self.precision],
            "input_resolution_seconds": RESOLUTIONS[self.precision],
            "mode": "instant" if self.is_instant else "interval",
            "start_local": self.start.astimezone(self.zone).isoformat(),
            "end_local_exclusive": self.end.astimezone(self.zone).isoformat(),
            "start_utc": self.start.isoformat(),
            "end_utc_exclusive": self.end.isoformat(),
            "elapsed_seconds": int((self.end - self.start).total_seconds()),
            "sampling_note": (
                "按输入的指定秒计算；分辨率 1 秒不代表天文模型误差为零。"
                if self.is_instant
                else "区间左闭右开，首末采样均在区间内；离散采样不构成连续变化的严格上下界。"
            ),
        }


def parse_time_input(value: str, timezone_name: str = "Asia/Shanghai") -> TimeWindow:
    if not isinstance(value, str):
        raise ValueError("日期时间必须是文本。")
    value = value.strip()
    match = PATTERN.fullmatch(value)
    if not match:
        raise ValueError("请输入 YYYY-MM-DD，或追加 HH、HH:MM、HH:MM:SS。")
    year, month, day, hour, minute, second = match.groups()
    precision = "second" if second else "minute" if minute else "hour" if hour else "day"
    if second == "60":
        raise ValueError("当前输入格式不支持直接表示闰秒 60，请使用相邻 UTC 秒核对。")
    try:
        naive = datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0)
        )
        zone = parse_timezone(timezone_name)
        start = localize(naive, zone).astimezone(UTC)
        end = (
            localize(naive + timedelta(days=1), zone).astimezone(UTC)
            if precision == "day"
            else start + timedelta(seconds=RESOLUTIONS[precision])
        )
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"日期时间无法解释：{exc}") from exc
    if end <= start:
        raise ValueError("时间区间为空，请检查日期与时区。")
    return TimeWindow(value, timezone_name.strip(), zone, precision, start, end)
