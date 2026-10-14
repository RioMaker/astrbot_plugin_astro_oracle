"""真实 SQLite 文件下的惰性创建、重开、并发、身份边界及连接释放检查。"""

import asyncio
import json
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from local_core.bot_commands import ChartRequest, ChartSettings
from local_core.ziwei_records import ZiweiCaller, ZiweiRecordStore

NOW = datetime(2026, 10, 14, 9, 30, tzinfo=timezone(timedelta(hours=8)))
SETTINGS = ChartSettings(default_time="08:15:30")
CALLER = ZiweiCaller("aiocqhttp", "bot-1", "group-1", "user-1", "message-1")


def read_rows(path, where="", values=()):
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row) for row in connection.execute("SELECT * FROM ziwei_calls " + where, values)
        ]


def test_caller_is_frozen_and_only_accepts_strings():
    with pytest.raises(FrozenInstanceError):
        CALLER.group_id = "other"
    with pytest.raises(TypeError):
        ZiweiCaller("aiocqhttp", "bot", "group", 123, "message")


def test_start_is_lazy_and_reopen_preserves_pending_and_completed_records(tmp_path):
    path = tmp_path / "nested" / "calls.sqlite3"
    store = ZiweiRecordStore(path)
    assert not path.parent.exists()

    async def exercise():
        first = await store.start(CALLER, "command", ChartRequest(time_text="2026"), SETTINGS, NOW)
        assert uuid.UUID(first).version == 4
        row = read_rows(path)[0]
        assert row["status"] == "pending" and row["result_json"] is None
        assert row["requested_at_utc"] == "2026-10-14T01:30:00.000000+00:00"
        defaults = json.loads(row["defaults_json"])
        assert defaults["completed_local_datetime"] == "2026-01-01T08:15:30"
        assert defaults["used_defaults"] == {
            "month": 1,
            "day": 1,
            "hour": 8,
            "minute": 15,
            "second": 30,
            "default_place": "北京",
        }
        result = {"epoch_utc": "2026-01-01T00:15:30+00:00", "timezone": "Asia/Shanghai"}
        await ZiweiRecordStore(path).finish(first, "sent", result=result)
        second = await ZiweiRecordStore(path).start(
            CALLER, "llm", ChartRequest(time_text="2026101412", place_text="上海"), SETTINGS, NOW
        )
        rows = {row["record_id"]: row for row in read_rows(path)}
        assert set(rows) == {first, second}
        assert rows[first]["status"] == "sent" and json.loads(rows[first]["result_json"]) == result
        assert rows[second]["status"] == "pending"
        defaults = json.loads(rows[second]["defaults_json"])
        assert defaults["used_defaults"] == {"minute": 15, "second": 30}
        assert defaults["effective_place_text"] == "上海"
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
            indexes = {r[1] for r in connection.execute("PRAGMA index_list(ziwei_calls)")}
            assert {"idx_ziwei_calls_group_user", "idx_ziwei_calls_user"} <= indexes

    asyncio.run(exercise())


def test_concurrent_instances_keep_group_user_and_record_identity_separate(tmp_path):
    path = tmp_path / "calls.sqlite3"
    callers = [
        ZiweiCaller("aiocqhttp", "bot", f"g-{i % 3}", f"u-{i % 4}", f"m-{i}") for i in range(36)
    ]

    async def one(i):
        store = ZiweiRecordStore(path)
        record_id = await store.start(
            callers[i],
            "llm" if i % 2 else "command",
            ChartRequest(time_text="20261014"),
            SETTINGS,
            NOW,
        )
        await store.finish(record_id, "sent", {"sample": i})
        return record_id

    async def exercise():
        identifiers = await asyncio.gather(*(one(i) for i in range(len(callers))))
        assert len(set(identifiers)) == len(callers)
        rows = {row["record_id"]: row for row in read_rows(path)}
        for i, identifier in enumerate(identifiers):
            row = rows[identifier]
            assert (row["group_id"], row["user_id"], row["message_id"]) == (
                callers[i].group_id,
                callers[i].user_id,
                callers[i].message_id,
            )
            assert row["status"] == "sent" and json.loads(row["result_json"]) == {"sample": i}
        scoped = read_rows(path, "WHERE group_id=? AND user_id=?", ("g-0", "u-0"))
        assert {row["message_id"] for row in scoped} == {"m-0", "m-12", "m-24"}

    asyncio.run(exercise())


def test_quoted_values_are_bound_as_data_and_failures_do_not_store_images(tmp_path):
    path = tmp_path / "calls.sqlite3"
    malicious = "x'); DROP TABLE ziwei_calls; --"
    caller = ZiweiCaller(*(malicious for _ in range(5)))

    async def exercise():
        store = ZiweiRecordStore(path)
        record_id = await store.start(
            caller,
            "command",
            ChartRequest(time_text="20261014", place_text=malicious),
            SETTINGS,
            NOW,
        )
        await store.finish(record_id, "send_failed", error_code="qq_send_failed")
        row = read_rows(path)[0]
        assert row["platform_name"] == row["group_id"] == row["user_id"] == malicious
        assert row["input_place_text"] == malicious and row["result_json"] is None
        assert row["error_code"] == "qq_send_failed" and row["status"] == "send_failed"
        assert not any("image" in name or "png" in name or "conversation" in name for name in row)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["calls.sqlite3"]

    asyncio.run(exercise())


@pytest.mark.parametrize("time_text", [None, "", " ", "20:00:00", "20260230"])
def test_missing_or_invalid_explicit_date_never_creates_database(tmp_path, time_text):
    path = tmp_path / "not-created" / "calls.sqlite3"

    async def exercise():
        with pytest.raises(ValueError):
            await ZiweiRecordStore(path).start(
                CALLER, "command", ChartRequest(time_text=time_text), SETTINGS, NOW
            )

    asyncio.run(exercise())
    assert not path.parent.exists()


@pytest.mark.parametrize("source,now", [("other", NOW), ("command", NOW.replace(tzinfo=None))])
def test_invalid_source_or_unzoned_request_time_does_not_create_database(tmp_path, source, now):
    path = tmp_path / "calls.sqlite3"

    async def exercise():
        with pytest.raises(ValueError):
            await ZiweiRecordStore(path).start(
                CALLER, source, ChartRequest(time_text="20261014"), SETTINGS, now
            )

    asyncio.run(exercise())
    assert not path.exists()


@pytest.mark.parametrize("status", ["sent", "send_failed", "failed", "cancelled"])
def test_terminal_status_is_persisted_and_cannot_be_overwritten(tmp_path, status):
    path = tmp_path / "calls.sqlite3"

    async def exercise():
        store = ZiweiRecordStore(path)
        record_id = await store.start(
            CALLER, "command", ChartRequest(time_text="20261014"), SETTINGS, NOW
        )
        await store.finish(
            record_id, status, error_code=None if status == "sent" else "classified_error"
        )
        with pytest.raises(ValueError):
            await store.finish(record_id, "failed")
        row = read_rows(path)[0]
        assert row["status"] == status and row["finished_at_utc"].endswith("+00:00")

    asyncio.run(exercise())


def test_unknown_id_is_an_error_and_finish_does_not_initialize_a_database(tmp_path):
    path = tmp_path / "absent" / "calls.sqlite3"

    async def exercise():
        store = ZiweiRecordStore(path)
        with pytest.raises(KeyError):
            await store.finish("missing", "failed")
        assert not path.parent.exists()
        await store.start(CALLER, "command", ChartRequest(time_text="20261014"), SETTINGS, NOW)
        with pytest.raises(KeyError):
            await store.finish("x'); DELETE FROM ziwei_calls; --", "failed")
        assert len(read_rows(path)) == 1

    asyncio.run(exercise())


def test_non_json_result_is_rejected_before_pending_record_is_changed(tmp_path):
    path = tmp_path / "calls.sqlite3"

    async def exercise():
        store = ZiweiRecordStore(path)
        record_id = await store.start(
            CALLER, "command", ChartRequest(time_text="20261014"), SETTINGS, NOW
        )
        for result in ({"png": b"image-bytes"}, {"number": float("nan")}):
            with pytest.raises((TypeError, ValueError)):
                await store.finish(record_id, "sent", result)
        assert read_rows(path)[0]["status"] == "pending"
        await store.finish(record_id, "failed", error_code="generation_failed")
        assert read_rows(path)[0]["result_json"] is None

    asyncio.run(exercise())


def test_connections_run_off_event_loop_and_release_file_handles(tmp_path, monkeypatch):
    path = tmp_path / "calls.sqlite3"
    main_thread = threading.get_ident()
    seen = []
    for method in ("_write_start", "_write_finish"):
        original = getattr(ZiweiRecordStore, method)

        def tracked(self, *args, original=original):
            seen.append(threading.get_ident())
            return original(self, *args)

        monkeypatch.setattr(ZiweiRecordStore, method, tracked)

    async def exercise():
        store = ZiweiRecordStore(path)
        record_id = await store.start(
            CALLER, "command", ChartRequest(time_text="20261014"), SETTINGS, NOW
        )
        await store.finish(record_id, "sent", {"timezone": "Asia/Shanghai"})

    asyncio.run(exercise())
    assert len(seen) == 2 and all(thread != main_thread for thread in seen)
    moved = path.with_name("moved.sqlite3")
    path.rename(moved)
    moved.unlink()


def test_newer_schema_is_not_silently_downgraded(tmp_path):
    path = tmp_path / "calls.sqlite3"

    async def exercise():
        store = ZiweiRecordStore(path)
        await store.start(CALLER, "command", ChartRequest(time_text="20261014"), SETTINGS, NOW)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA user_version=2")
            connection.commit()
        with pytest.raises(RuntimeError):
            await store.start(CALLER, "command", ChartRequest(time_text="20261014"), SETTINGS, NOW)
        assert len(read_rows(path)) == 1
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 2

    asyncio.run(exercise())
