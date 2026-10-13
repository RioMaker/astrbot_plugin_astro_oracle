"""模拟 AstrBot API 的消息隔离验收；不代表真实平台已加载。"""

import asyncio
import importlib.util
import inspect
import sys
import types
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def adapter(monkeypatch, tmp_path):
    for name in (
        "astrbot",
        "astrbot.api",
        "astrbot.api.event",
        "astrbot.api.message_components",
        "astrbot.api.star",
        "astrbot.core",
        "astrbot.core.star",
        "astrbot.core.star.filter",
        "astrbot.core.star.filter.command",
        "astrbot.core.utils",
        "astrbot.core.utils.astrbot_path",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    class Component:
        def __init__(self, text):
            self.text = text

        @staticmethod
        def fromBytes(value):
            return types.SimpleNamespace(png=value)

    class Star:
        def __init__(self, context):
            self.context = context

    def command(name, alias):
        def decorate(handler):
            handler.command_name, handler.command_aliases = name, alias
            return handler

        return decorate

    api = sys.modules["astrbot.api"]
    api.AstrBotConfig = dict
    api.logger = types.SimpleNamespace(exception=lambda *args: None)
    event_api = sys.modules["astrbot.api.event"]
    event_api.AstrMessageEvent = object
    event_api.MessageChain = lambda chain: types.SimpleNamespace(chain=chain)
    event_api.filter = types.SimpleNamespace(command=command)
    comp_api = sys.modules["astrbot.api.message_components"]
    comp_api.Image = comp_api.Plain = Component
    sys.modules["astrbot.api.star"].Star = Star
    sys.modules["astrbot.api.star"].Context = object
    sys.modules["astrbot.core.star.filter.command"].GreedyStr = str
    sys.modules["astrbot.core.utils.astrbot_path"].get_astrbot_data_path = lambda: str(tmp_path)

    package = types.ModuleType("astro_entry_test")
    package.__path__ = [str(ROOT)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    name = "astro_entry_test.main"
    spec = importlib.util.spec_from_file_location(name, ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)

    class Service:
        ready = True

        def __init__(self, data_dir):
            self.data_dir = data_dir
            self.calls = []
            self.ziwei_calls = []
            self.closed = False
            self.close_count = 0
            self.error = None

        async def generate(self, request, settings, now):
            self.calls.append((request, settings, now))
            if self.error:
                raise self.error
            return b"png-fixture-for-routing-only"

        async def generate_ziwei(self, request, settings, now):
            self.ziwei_calls.append((request, settings, now))
            if self.error:
                raise self.error
            return b"ziwei-png-fixture-for-routing-only"

        async def close(self):
            self.closed = True
            self.close_count += 1

    module.ChartService = Service
    yield module, tmp_path
    for key in list(sys.modules):
        if key.startswith("astro_entry_test.local_core"):
            sys.modules.pop(key)


class Event:
    def __init__(self, origin="test:GroupMessage:100"):
        self.unified_msg_origin = origin
        self.stopped = False

    def stop_event(self):
        self.stopped = True

    def plain_result(self, value):
        return value


class Context:
    def __init__(self):
        self.sent = []

    async def send_message(self, origin, message):
        self.sent.append((origin, message.chain))


async def consume(plugin, event, content, handler="star_chart"):
    start = len(plugin.context.sent)
    await getattr(plugin, handler)(event, content)
    return [c.text for _, chain in plugin.context.sent[start:] for c in chain if hasattr(c, "text")]


def test_one_dedicated_command_registers_every_prefix_and_framework_data_dir(adapter):
    module, data_root = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    assert plugin.star_chart.command_name == "星图"
    assert plugin.star_chart.command_aliases == {"xingtu", "xt", "star"}
    assert plugin._charts.data_dir == data_root / "plugin_data" / "astrbot_plugin_astro_oracle"
    assert not hasattr(plugin, "astro_oracle")


@pytest.mark.parametrize("content", ["help", "帮助", "time bad", "20250"])
def test_help_and_syntax_errors_do_not_prepare_data(adapter, content):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {"default_time": "13:27:41"})
    event = Event()
    result = asyncio.run(consume(plugin, event, content))
    assert result and event.stopped
    assert not plugin._charts.calls
    assert len(plugin.context.sent) == 1
    assert plugin.context.sent[0][0] == event.unified_msg_origin
    if content in {"help", "帮助"}:
        assert "13:27:41" in result[0]


def test_disabled_command_does_not_generate(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {"enabled": False})
    assert "已关闭" in asyncio.run(consume(plugin, Event(), ""))[0]
    assert not plugin._charts.calls


def test_bare_command_uses_request_instant_and_beijing(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    assert not asyncio.run(consume(plugin, Event(), ""))
    request, settings, now = plugin._charts.calls[0]
    assert request.time_text is None and settings.default_place == "北京"
    assert now.tzinfo is not None
    assert plugin.context.sent[0][1][0].png.startswith(b"png-")


def test_shared_event_and_config_mutation_do_not_change_first_request_route(adapter):
    module, _ = adapter
    config = {"default_time": "12:00:00"}
    plugin = module.AstroOraclePlugin(Context(), config)
    event = Event("test:GroupMessage:first")

    async def exercise():
        entered, resume = asyncio.Event(), asyncio.Event()

        async def generate(request, settings, now):
            if request.time_text == "2026-10-10":
                entered.set()
                await resume.wait()
                assert settings.default_time == "08:00:00"
                return b"first-image"
            assert settings.default_time == "15:42:07"
            return b"second-image"

        plugin._charts.generate = generate
        task = asyncio.create_task(consume(plugin, event, "time 2026-10-10"))
        await entered.wait()
        event.unified_msg_origin = "test:GroupMessage:second"
        config["default_time"] = "15:42:07"
        await consume(plugin, event, "at 2026-10-11 上海")
        resume.set()
        await task

    asyncio.run(exercise())
    assert [(origin, chain[0].png) for origin, chain in plugin.context.sent] == [
        ("test:GroupMessage:second", b"second-image"),
        ("test:GroupMessage:first", b"first-image"),
    ]


@pytest.mark.parametrize(
    "error,expected",
    [(ValueError("地点有多个匹配"), "多个匹配"), (RuntimeError("internal-only"), "生成失败")],
)
def test_error_is_sent_to_same_origin_without_fake_image(adapter, error, expected):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    plugin._charts.error = error
    asyncio.run(consume(plugin, Event(), "place 北京"))
    origin, chain = plugin.context.sent[0]
    assert origin == "test:GroupMessage:100" and expected in chain[0].text
    assert not hasattr(chain[0], "png")


def test_resource_progress_and_terminate(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    plugin._charts.ready = False
    values = asyncio.run(consume(plugin, Event(), "place 上海"))
    assert "准备星图资源" in values[0]
    assert "首次" not in values[0]
    assert "会复用" in values[0]
    assert len(plugin._charts.calls) == 1
    assert len(plugin.context.sent) == 2
    assert plugin.context.sent[-1][1][0].png.startswith(b"png-")
    asyncio.run(plugin.terminate())
    assert plugin._charts.closed


def test_resource_timeout_explains_source_and_reuses_cache_on_each_attempt(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    plugin._charts.ready = False
    plugin._charts.error = module.ResourceDownloadError(
        "JPL DE440s 历表", httpx.ConnectTimeout("private proxy details must not be echoed")
    )
    for _ in range(2):
        replies = asyncio.run(consume(plugin, Event(), ""))
        assert len(replies) == 2
        assert "首次" not in replies[0]
        assert "JPL DE440s" in replies[1] and "连接下载站点超时" in replies[1]
        assert "离线资源包" in replies[1] and "会复用" in replies[1]
        assert "private proxy" not in replies[1]
    assert all(not hasattr(c, "png") for _, chain in plugin.context.sent for c in chain)


def test_ziwei_command_is_independent_and_both_handlers_are_plain_coroutines(adapter):
    module, data_root = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    old_names = {plugin.star_chart.command_name} | plugin.star_chart.command_aliases
    new_names = {plugin.ziwei_chart.command_name} | plugin.ziwei_chart.command_aliases
    assert old_names == {"星图", "xingtu", "xt", "star"}
    assert new_names == {"紫微星图", "紫薇星图"} and old_names.isdisjoint(new_names)
    assert plugin.ziwei_chart.command_name == "紫微星图"
    assert plugin.ziwei_chart.command_aliases == {"紫薇星图"}
    for handler in (plugin.star_chart, plugin.ziwei_chart):
        assert inspect.iscoroutinefunction(handler)
        assert not inspect.isasyncgenfunction(handler)
    assert plugin._charts.data_dir == data_root / "plugin_data" / "astrbot_plugin_astro_oracle"
    assert not hasattr(plugin, "_ziwei_charts")


@pytest.mark.parametrize("content", ["help", "帮助", "help 北京", "time bad", "20250"])
def test_ziwei_help_and_syntax_errors_use_own_command_without_preparing_data(adapter, content):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {"default_time": "13:27:41"})
    event = Event()
    replies = asyncio.run(consume(plugin, event, content, "ziwei_chart"))
    assert event.stopped and len(replies) == 1
    assert "/紫微星图" in replies[0] and "/星图" not in replies[0]
    assert "/紫薇星图" in replies[0]
    assert not plugin._charts.calls and not plugin._charts.ziwei_calls
    assert plugin.context.sent[0][0] == event.unified_msg_origin
    if content in {"help", "帮助"}:
        assert "13:27:41" in replies[0]


def test_ziwei_disabled_command_does_not_generate(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {"enabled": False})
    replies = asyncio.run(consume(plugin, Event(), "", "ziwei_chart"))
    assert "紫微星图功能当前已关闭" in replies[0]
    assert not plugin._charts.calls and not plugin._charts.ziwei_calls


def test_ziwei_bare_command_routes_only_to_own_service_method(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    assert not asyncio.run(consume(plugin, Event(), "", "ziwei_chart"))
    assert not plugin._charts.calls
    request, settings, now = plugin._charts.ziwei_calls[0]
    assert request.time_text is None and settings.default_place == "北京"
    assert now.tzinfo is not None
    assert len(plugin.context.sent) == 1
    assert plugin.context.sent[0][1][0].png.startswith(b"ziwei-png-")


def test_ziwei_and_old_request_keep_their_routes_when_event_and_config_change(adapter):
    module, _ = adapter
    config = {"default_time": "12:00:00"}
    plugin = module.AstroOraclePlugin(Context(), config)
    event = Event("test:GroupMessage:ziwei-first")

    async def exercise():
        entered, resume = asyncio.Event(), asyncio.Event()

        async def generate_ziwei(request, settings, now):
            entered.set()
            await resume.wait()
            assert request.time_text == "20261012"
            assert request.timezone_override == "UTC+08:00"
            assert settings.default_time == "08:00:00" and now.tzinfo is not None
            return b"ziwei-first-image"

        plugin._charts.generate_ziwei = generate_ziwei
        first = asyncio.create_task(
            consume(plugin, event, "北京 20261012 tz=UTC+08:00", "ziwei_chart")
        )
        await entered.wait()
        event.unified_msg_origin = "test:GroupMessage:old-second"
        config["default_time"] = "15:42:07"
        await consume(plugin, event, "上海 20261013")
        resume.set()
        await first

    asyncio.run(exercise())
    assert plugin._charts.calls[0][1].default_time == "15:42:07"
    assert [(origin, chain[0].png) for origin, chain in plugin.context.sent] == [
        ("test:GroupMessage:old-second", b"png-fixture-for-routing-only"),
        ("test:GroupMessage:ziwei-first", b"ziwei-first-image"),
    ]


@pytest.mark.parametrize(
    "error,expected",
    [
        (ValueError("地点有多个匹配，使用 /星图 place 查看候选"), "多个匹配"),
        (RuntimeError("internal-only"), "紫微星图生成失败"),
    ],
)
def test_ziwei_errors_keep_route_without_image_or_old_help(adapter, error, expected):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    plugin._charts.error = error
    asyncio.run(consume(plugin, Event(), "北京 20261012", "ziwei_chart"))
    origin, chain = plugin.context.sent[0]
    assert origin == "test:GroupMessage:100" and expected in chain[0].text
    assert "/星图" not in chain[0].text and "internal-only" not in chain[0].text
    assert not hasattr(chain[0], "png") and not plugin._charts.calls


def test_ziwei_cold_request_completes_and_terminate_closes_shared_owner_once(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    plugin._charts.ready = False
    replies = asyncio.run(consume(plugin, Event(), "北京 20261012", "ziwei_chart"))
    assert "准备紫微星图资源" in replies[0] and "会复用" in replies[0]
    assert len(plugin._charts.ziwei_calls) == 1 and not plugin._charts.calls
    assert len(plugin.context.sent) == 2
    assert plugin.context.sent[-1][1][0].png.startswith(b"ziwei-png-")
    asyncio.run(plugin.terminate())
    assert plugin._charts.closed and plugin._charts.close_count == 1


def test_ziwei_resource_failure_preserves_safe_source_message(adapter):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    plugin._charts.ready = False
    plugin._charts.error = module.ResourceDownloadError(
        "JPL DE440s 历表", httpx.ConnectTimeout("private proxy details must not be echoed")
    )
    replies = asyncio.run(consume(plugin, Event(), "", "ziwei_chart"))
    assert len(replies) == 2
    assert "JPL DE440s" in replies[1] and "连接下载站点超时" in replies[1]
    assert "离线资源包" in replies[1] and "会复用" in replies[1]
    assert "private proxy" not in replies[1]
    assert not plugin._charts.calls
    assert all(not hasattr(c, "png") for _, chain in plugin.context.sent for c in chain)


@pytest.mark.parametrize("prefix", ["紫微星图", "紫薇星图"])
def test_both_ziwei_spellings_select_one_handler_and_the_same_service(adapter, prefix):
    module, _ = adapter
    plugin = module.AstroOraclePlugin(Context(), {})
    handlers = [
        handler
        for handler in (plugin.star_chart, plugin.ziwei_chart)
        if prefix == handler.command_name or prefix in handler.command_aliases
    ]
    assert handlers == [plugin.ziwei_chart]
    event = Event()
    asyncio.run(handlers[0](event, "北京 20261012200000"))
    assert event.stopped and not plugin._charts.calls
    request, _, _ = plugin._charts.ziwei_calls[0]
    assert request.place_text == "北京" and request.time_text == "20261012200000"
    assert len(plugin.context.sent) == 1
    assert plugin.context.sent[0][1][0].png.startswith(b"ziwei-png-")
