"""QQ 群身份、命令/模型调用及 SQLite 的本地闭环；不代表真实 QQ 收图。"""

import asyncio
import importlib
import io
import json
import sqlite3
import threading
from contextlib import closing
from types import SimpleNamespace

import pytest
from PIL import Image
from test_bot_entry import Context, Event
from test_bot_entry import adapter as adapter


class QQEvent(Event):
    def __init__(self, group="group-1", user="member-1", platform="aiocqhttp", instance="qq-1"):
        super().__init__(f"{instance}:GroupMessage:{group}")
        self.group, self.user, self.platform, self.instance = group, user, platform, instance
        self.message_obj = SimpleNamespace(message_id="message-1")

    def get_platform_name(self):
        return self.platform

    def get_platform_id(self):
        return self.instance

    def get_group_id(self):
        return self.group

    def get_sender_id(self):
        return self.user


def rows(plugin):
    path = plugin._charts.data_dir / "ziwei_calls.sqlite3"
    if not path.exists():
        return []
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT * FROM ziwei_calls ORDER BY rowid")]


@pytest.mark.parametrize("source", ["command", "llm"])
def test_explicit_date_is_recorded_for_actual_group_member_and_appended(adapter, source):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    event = QQEvent()

    async def exercise():
        for query in ("20261014200000", "20261015"):
            if source == "command":
                await plugin.ziwei_chart(event, query)
            else:
                result = json.loads(await plugin.generate_ziwei_chart(event, query))
                assert result["status"] == "sent" and result["recorded"]
                assert result["chart"]["timezone"] == "Asia/Shanghai"

    asyncio.run(exercise())
    records = rows(plugin)
    assert len(records) == 2 and records[0]["record_id"] != records[1]["record_id"]
    assert [r["input_time_text"] for r in records] == ["20261014200000", "20261015"]
    for row in records:
        assert (row["platform_id"], row["group_id"], row["user_id"]) == (
            "qq-1",
            "group-1",
            "member-1",
        )
        assert row["source"] == source and row["status"] == "sent"
        assert json.loads(row["result_json"])["timezone"] == "Asia/Shanghai"
        assert row["message_id"] == "message-1" and row["error_code"] is None
    assert event.stopped == (source == "command")
    assert len(plugin.context.sent) == 2 and not plugin._charts.calls


@pytest.mark.parametrize(
    "query,event,config,handler",
    [
        ("", QQEvent(), {}, "ziwei_chart"),
        ("北京", QQEvent(), {}, "generate_ziwei_chart"),
        ("help", QQEvent(), {}, "ziwei_chart"),
        ("20260230", QQEvent(), {}, "generate_ziwei_chart"),
        ("20261014", QQEvent(group=""), {}, "ziwei_chart"),
        ("20261014", QQEvent(platform="telegram"), {}, "generate_ziwei_chart"),
        ("20261014", QQEvent(user=""), {}, "ziwei_chart"),
        ("20261014", QQEvent(), {"record_ziwei_queries": False}, "generate_ziwei_chart"),
        ("20261014", QQEvent(), {"enabled": False}, "ziwei_chart"),
        ("20261014", QQEvent(), {}, "star_chart"),
    ],
)
def test_only_dated_qq_group_ziwei_queries_create_a_database(
    adapter, query, event, config, handler
):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), config)
    asyncio.run(getattr(plugin, handler)(event, query))
    assert not (plugin._charts.data_dir / "ziwei_calls.sqlite3").exists()


@pytest.mark.parametrize("config", [{"enabled": False}, {"enable_ziwei_llm_tool": False}])
def test_disabled_llm_tool_does_not_send_compute_or_record(adapter, config):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), config)
    event = QQEvent()
    result = json.loads(asyncio.run(plugin.generate_ziwei_chart(event, "20261014")))
    assert result["status"] == "disabled" and not event.stopped
    assert not plugin._charts.ziwei_calls and not plugin.context.sent and not rows(plugin)


def test_missing_tool_argument_reports_error_instead_of_using_current_date(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    result = json.loads(asyncio.run(plugin.generate_ziwei_chart(QQEvent())))
    assert result["status"] == "invalid_request"
    assert not plugin._charts.ziwei_calls and not rows(plugin)


def test_group_sender_route_and_record_setting_are_frozen_before_await(adapter):
    module, _ = adapter
    config = {"default_time": "13:27:41"}
    plugin = module.AstroOraclePlugin(Context(), config)
    event = QQEvent()

    async def exercise():
        entered, resume = asyncio.Event(), asyncio.Event()
        original = plugin._charts.generate_ziwei_result

        async def blocked(request, settings, now):
            entered.set()
            await resume.wait()
            assert settings.default_time == "13:27:41"
            return await original(request, settings, now)

        plugin._charts.generate_ziwei_result = blocked
        task = asyncio.create_task(plugin.generate_ziwei_chart(event, "20261014"))
        await entered.wait()
        event.group, event.user, event.instance = "group-2", "member-2", "qq-2"
        event.message_obj.message_id = "message-2"
        event.unified_msg_origin = "qq-2:GroupMessage:group-2"
        config.update(record_ziwei_queries=False, default_time="17:00:00")
        resume.set()
        result = json.loads(await task)
        assert result["recorded"]

    asyncio.run(exercise())
    record = rows(plugin)[0]
    assert (record["platform_id"], record["group_id"], record["user_id"], record["message_id"]) == (
        "qq-1",
        "group-1",
        "member-1",
        "message-1",
    )
    assert plugin.context.sent[0][0] == "qq-1:GroupMessage:group-1"


@pytest.mark.parametrize("send_failure", [False, True])
def test_failed_generation_and_delivery_have_distinct_persistent_states(adapter, send_failure):
    module, _ = adapter
    context = Context()
    plugin = module.AstroOraclePlugin(context, {})
    if send_failure:

        async def failed_send(origin, message):
            return False

        context.send_message = failed_send
    else:
        plugin._charts.error = RuntimeError("internal-private-details")
    result = json.loads(asyncio.run(plugin.generate_ziwei_chart(QQEvent(), "20261014")))
    record = rows(plugin)[0]
    assert result["recorded"]
    assert result["status"] == record["status"] == ("send_failed" if send_failure else "failed")
    assert record["error_code"] == ("send_failed" if send_failure else "generation_failed")
    assert bool(record["result_json"]) == send_failure
    assert "internal-private-details" not in json.dumps(result)


@pytest.mark.parametrize("method", ["start", "finish"])
def test_storage_failure_keeps_image_delivery_but_reports_unrecorded_result(adapter, method):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})

    async def fail(*args):
        raise OSError("private local path")

    setattr(plugin._ziwei_records, method, fail)
    result = json.loads(asyncio.run(plugin.generate_ziwei_chart(QQEvent(), "20261014")))
    assert result["status"] == "sent" and not result["recorded"]
    assert "record_warning" in result and "private local path" not in json.dumps(result)
    assert len(plugin.context.sent) == 1


def test_cancelled_call_finishes_record_without_sending_image(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})

    async def exercise():
        entered = asyncio.Event()

        async def blocked(*args):
            entered.set()
            await asyncio.Event().wait()

        plugin._charts.generate_ziwei_result = blocked
        task = asyncio.create_task(plugin.generate_ziwei_chart(QQEvent(), "20261014"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert rows(plugin)[0]["status"] == "cancelled"
    assert not plugin.context.sent


def test_real_command_and_llm_share_the_same_png_and_persist_its_actual_metadata(adapter):
    module, _ = adapter
    module.ChartService = importlib.import_module(
        "astro_entry_test.local_core.bot_service"
    ).ChartService
    plugin = module.AstroOraclePlugin(Context(), {})

    async def exercise():
        try:
            await plugin.ziwei_chart(QQEvent(), "20261014200000")
            event = QQEvent(group="group-2", user="member-2")
            outcome = json.loads(await plugin.generate_ziwei_chart(event, "20261014200000"))
            assert outcome["status"] == "sent" and outcome["recorded"] and not event.stopped
            images = [c.png for _, chain in plugin.context.sent for c in chain if hasattr(c, "png")]
            assert len(images) == 2 and images[0] == images[1]
            with Image.open(io.BytesIO(images[0])) as image:
                assert image.format == "PNG" and image.size == (2440, 1810)
                image.verify()
            records = rows(plugin)
            assert [record["source"] for record in records] == ["command", "llm"]
            assert [record["group_id"] for record in records] == ["group-1", "group-2"]
            for record in records:
                metadata = json.loads(record["result_json"])
                assert metadata == outcome["chart"]
                assert metadata["epoch_utc"] == "2026-10-14T12:00:00+00:00"
                assert metadata["epoch_local"] == "2026-10-14T20:00:00+08:00"
                assert metadata["site"]["label"] == "北京"
                assert metadata["timezone"] == "Asia/Shanghai"
                assert metadata["traditional"]["lunar"]["day"] == 5
        finally:
            await plugin.terminate()

    asyncio.run(exercise())
    assert not plugin._charts.ready


@pytest.mark.parametrize("phase", ["start", "finish"])
def test_cancel_during_sqlite_write_preserves_cancelled_or_already_sent_state(adapter, phase):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    release = threading.Event()

    async def exercise():
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()
        method = "_write_start" if phase == "start" else "_write_finish"
        original = getattr(plugin._ziwei_records, method)

        def blocked(*args):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5)
            return original(*args)

        setattr(plugin._ziwei_records, method, blocked)
        task = asyncio.create_task(plugin.generate_ziwei_chart(QQEvent(), "20261014"))
        try:
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()  # 收尾等待已有写入，不能取消 SQLite 的排队任务。
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(exercise())
    assert rows(plugin)[0]["status"] == ("cancelled" if phase == "start" else "sent")
    assert len(plugin.context.sent) == (0 if phase == "start" else 1)


@pytest.mark.parametrize(
    "raw_group,expected", [("group-1", True), (None, False), ("another", False)]
)
def test_official_qq_records_real_groups_but_not_channels(adapter, raw_group, expected):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    event = QQEvent(platform="qq_official")
    event.message_obj.raw_message = (
        SimpleNamespace(group_openid=raw_group, author=SimpleNamespace(member_openid="member-1"))
        if raw_group is not None
        else SimpleNamespace(channel_id="group-1", guild_id="guild-1")
    )
    outcome = json.loads(asyncio.run(plugin.generate_ziwei_chart(event, "20261014")))
    assert outcome["status"] == "sent" and outcome["recorded"] == expected
    assert bool(rows(plugin)) == expected
