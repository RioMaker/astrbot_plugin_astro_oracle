"""显式紫微星图调用的短连接 SQLite 记录；不接收对话正文或图片。"""

import asyncio
import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from .bot_commands import ChartRequest, ChartSettings, default_clock, validate_time_text

SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000
SOURCES = frozenset(("command", "llm"))
FINAL_STATUSES = frozenset(("sent", "send_failed", "failed", "cancelled"))
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS ziwei_calls (
        record_id TEXT PRIMARY KEY,
        requested_at_utc TEXT NOT NULL,
        finished_at_utc TEXT,
        platform_name TEXT NOT NULL,
        platform_id TEXT NOT NULL,
        group_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        message_id TEXT NOT NULL,
        source TEXT NOT NULL CHECK (source IN ('command', 'llm')),
        input_time_text TEXT NOT NULL,
        input_place_text TEXT,
        input_timezone_override TEXT,
        defaults_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK
            (status IN ('pending', 'sent', 'send_failed', 'failed', 'cancelled')),
        result_json TEXT,
        error_code TEXT
    )""",
    """CREATE INDEX IF NOT EXISTS idx_ziwei_calls_group_user
       ON ziwei_calls (platform_name, platform_id, group_id, user_id, requested_at_utc)""",
    """CREATE INDEX IF NOT EXISTS idx_ziwei_calls_user
       ON ziwei_calls (platform_name, platform_id, user_id, requested_at_utc)""",
)
_INSERT = """INSERT INTO ziwei_calls (
    record_id, requested_at_utc, platform_name, platform_id, group_id, user_id, message_id,
    source, input_time_text, input_place_text, input_timezone_override, defaults_json, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')"""


@dataclass(frozen=True)
class ZiweiCaller:
    platform_name: str
    platform_id: str
    group_id: str
    user_id: str
    message_id: str

    def __post_init__(self):
        if any(not isinstance(getattr(self, field.name), str) for field in fields(self)):
            raise TypeError("调用身份的全部字段须为字符串。")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _utc_text(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("调用时间须为带时区的 datetime。")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _defaults(request, settings):
    parts = validate_time_text(request.time_text)
    clock = default_clock(settings.default_time)
    fallback = (None, 1, 1, clock.hour, clock.minute, clock.second)
    names = ("year", "month", "day", "hour", "minute", "second")
    completed = [int(part) if part is not None else fallback[i] for i, part in enumerate(parts)]
    used = {names[i]: fallback[i] for i, part in enumerate(parts) if part is None}
    if not request.place_text:
        used["default_place"] = settings.default_place
    return {
        "default_place": settings.default_place,
        "default_time": settings.default_time,
        "coordinate_timezone": settings.coordinate_timezone,
        "effective_place_text": request.place_text or settings.default_place,
        # 城市时区需由地点库确定，实际 UTC/时区应从 finish 的 normalized 元数据读取。
        "completed_local_datetime": datetime(*completed).isoformat(),
        "used_defaults": used,
    }


class ZiweiRecordStore:
    def __init__(self, path):
        self.path = Path(path)

    async def start(self, caller, source, request, settings, now):
        """仅显式合法日期创建 pending 记录；全部磁盘操作放在短期工作线程中。"""
        if not isinstance(caller, ZiweiCaller):
            raise TypeError("调用身份须为 ZiweiCaller。")
        if source not in SOURCES:
            raise ValueError("调用来源须为 command 或 llm。")
        if not isinstance(request, ChartRequest) or not isinstance(settings, ChartSettings):
            raise TypeError("请求和配置须为 ChartRequest 与 ChartSettings。")
        if not isinstance(request.time_text, str) or not request.time_text.strip():
            raise ValueError("调用记录须提供显式日期时间，不能使用当前时间兜底。")
        for value in (request.place_text, request.timezone_override):
            if value is not None and not isinstance(value, str):
                raise TypeError("输入地点和时区须为字符串或 None。")
        requested_at = _utc_text(now)
        defaults_json = _json(_defaults(request, settings))
        record_id = str(uuid.uuid4())
        values = (
            record_id,
            requested_at,
            caller.platform_name,
            caller.platform_id,
            caller.group_id,
            caller.user_id,
            caller.message_id,
            source,
            request.time_text,
            request.place_text,
            request.timezone_override,
            defaults_json,
        )
        await asyncio.to_thread(self._write_start, values)
        return record_id

    def _write_start(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA_VERSION):
                    raise RuntimeError(f"不支持的紫微调用记录版本：{version}")
                for statement in _SCHEMA:
                    connection.execute(statement)
                if version == 0:
                    connection.execute("PRAGMA user_version = 1")
                connection.execute(_INSERT, values)

    async def finish(self, record_id, status, result=None, error_code=None):
        """将已有 pending 记录结束；结果只接受 JSON-safe 元数据字典。"""
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("记录 ID 须为非空字符串。")
        if status not in FINAL_STATUSES:
            raise ValueError("记录状态须为 sent、send_failed、failed 或 cancelled。")
        if result is not None and not isinstance(result, dict):
            raise TypeError("结果须为 JSON-safe 元数据字典或 None。")
        if error_code is not None and not isinstance(error_code, str):
            raise TypeError("错误分类须为字符串或 None，不接收异常对象。")
        result_json = _json(result) if result is not None else None
        finished_at = _utc_text(datetime.now(timezone.utc))
        await asyncio.to_thread(
            self._write_finish, record_id, status, result_json, error_code, finished_at
        )

    def _write_finish(self, record_id, status, result_json, error_code, finished_at):
        if not self.path.is_file():
            raise KeyError(record_id)
        # mode=rw 避免未知 ID 或外部删除数据库后，finish 意外创建新库。
        uri = self.path.resolve().as_uri() + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000)) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version != SCHEMA_VERSION:
                    raise RuntimeError(f"不支持的紫微调用记录版本：{version}")
                cursor = connection.execute(
                    """UPDATE ziwei_calls
                       SET status=?, result_json=?, error_code=?, finished_at_utc=?
                       WHERE record_id=? AND status='pending'""",
                    (status, result_json, error_code, finished_at, record_id),
                )
                if cursor.rowcount != 1:
                    found = connection.execute(
                        "SELECT status FROM ziwei_calls WHERE record_id=?", (record_id,)
                    ).fetchone()
                    if found is None:
                        raise KeyError(record_id)
                    raise ValueError("这条调用记录已经结束。")
