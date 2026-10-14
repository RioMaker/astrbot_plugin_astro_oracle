"""使用官方 4.28.1 调度/事件/调用代码复现首次无响应；消息 API 为隔离协作者。"""

import ast
import asyncio
import copy
import hashlib
import inspect
import json
import types
import typing
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import httpx

from local_core.bot_commands import ChartSettings, help_text, parse_request
from local_core.resources import ResourceDownloadError
from local_core.ziwei_invocation import capture_qq_caller

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "astrbot-reference"
FILES = {
    "scheduler-v4.28.1.py": "astrbot/core/pipeline/scheduler.py",
    "event-v4.28.1.py": "astrbot/core/platform/astr_message_event.py",
    "context-utils-v4.28.1.py": "astrbot/core/pipeline/context_utils.py",
}


class Chain:
    def __init__(self, chain=None):
        self.chain = chain or []
        self.stopped = False

    def stop_event(self):
        self.stopped = True
        return self

    def is_stopped(self):
        return self.stopped

    def message(self, text):
        self.chain.append(types.SimpleNamespace(text=text))
        return self


def load_function(path, name, namespace, class_name=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if class_name:
        tree = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    node = copy.deepcopy(
        next(
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
        )
    )
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def prepare_namespace():
    namespace = {
        "AsyncGenerator": AsyncGenerator,
        "asyncio": asyncio,
        "cast": cast,
        "T": typing,
        "inspect": inspect,
        "AstrMessageEvent": object,
        "MessageChain": Chain,
        "MessageEventResult": Chain,
        "CommandResult": Chain,
        "GreedyStr": str,
        "datetime": datetime,
        "timezone": timezone,
        "ChartSettings": ChartSettings,
        "parse_request": parse_request,
        "help_text": help_text,
        "ResourceDownloadError": ResourceDownloadError,
        "capture_qq_caller": capture_qq_caller,
        "Plain": lambda text: types.SimpleNamespace(text=text),
        "Image": types.SimpleNamespace(fromBytes=lambda png: types.SimpleNamespace(png=png)),
        "logger": types.SimpleNamespace(
            debug=lambda *args: None, error=lambda *args, **kw: None, exception=lambda *args: None
        ),
    }
    methods = {
        name: load_function(REFERENCE / "event-v4.28.1.py", name, namespace, "AstrMessageEvent")
        for name in ("set_result", "stop_event", "is_stopped", "plain_result")
    }
    event_type = type("OfficialEventMethods", (), methods)
    namespace["AstrMessageEvent"] = event_type
    wrapper = load_function(REFERENCE / "context-utils-v4.28.1.py", "call_handler", namespace)
    scheduler_method = load_function(
        REFERENCE / "scheduler-v4.28.1.py", "_process_stages", namespace, "PipelineScheduler"
    )
    scheduler_type = type("OfficialSchedulerMethod", (), {"_process_stages": scheduler_method})
    return namespace, event_type, wrapper, scheduler_type


async def run_case(source, content, ready=True, enabled=True, handler_name="star_chart"):
    namespace, event_type, wrapper, scheduler_type = prepare_namespace()
    if handler_name == "ziwei_chart":
        for helper in ("ziwei_help", "ziwei_error_text"):
            load_function(source, helper, namespace)
    method = load_function(source, handler_name, namespace, "AstroOraclePlugin")
    if handler_name == "ziwei_chart":
        assert inspect.iscoroutinefunction(method) and not inspect.isasyncgenfunction(method)
    sent, computed = [], []
    service_calls = []

    async def send(origin, message):
        sent.extend((origin, component) for component in message.chain)
        return True

    async def generate(*args):
        computed.append(args)
        service_calls.append("star_chart")
        return b"message-routing-only; not astronomy fixture"

    async def generate_ziwei(*args):
        computed.append(args)
        service_calls.append("ziwei_chart")
        return types.SimpleNamespace(
            png=b"ziwei-message-routing-only; not astronomy fixture", metadata={}
        )

    plugin = types.SimpleNamespace(
        context=types.SimpleNamespace(send_message=send),
        config={"enabled": enabled},
        _charts=types.SimpleNamespace(
            ready=ready, generate=generate, generate_ziwei_result=generate_ziwei
        ),
    )
    if handler_name == "ziwei_chart":
        for helper in ("_finish_ziwei_record", "_run_ziwei"):
            function = load_function(source, helper, namespace, "AstroOraclePlugin")
            setattr(plugin, helper, function.__get__(plugin))
    event = event_type()
    event.get_platform_name = lambda: "test"
    event._result, event._force_stopped = None, False
    event.unified_msg_origin = "test:GroupMessage:sky"

    class Process:
        async def process(self, event):
            async for value in wrapper(event, method.__get__(plugin), content):
                yield value

    class Respond:
        async def process(self, event):
            if event._result and event._result.chain:
                await send(event.unified_msg_origin, event._result)

    scheduler = scheduler_type()
    scheduler.stages = [Process(), Respond()]
    await scheduler._process_stages(event)
    assert all(origin == "test:GroupMessage:sky" for origin, _ in sent)
    assert all(name == handler_name for name in service_calls)
    if handler_name == "ziwei_chart":
        assert event.is_stopped()
        text_messages = [c.text for _, c in sent if hasattr(c, "text")]
        assert all("/星图" not in value for value in text_messages)
        if computed and not ready:
            assert "准备紫微星图资源" in text_messages[0]
        elif content in {"help", "帮助", "20250", "help 北京"} and enabled:
            assert "/紫微星图" in text_messages[0]
            assert "/紫薇星图" in text_messages[0]
        if not enabled:
            assert "紫微星图功能当前已关闭" in text_messages[0]
    return {
        "text_messages": sum(hasattr(c, "text") for _, c in sent),
        "image_messages": sum(hasattr(c, "png") for _, c in sent),
        "calculations_started": len(computed),
    }


async def verify():
    results = []
    previous = REFERENCE / "main-before-response-fix.py"
    if previous.exists():
        for content in ("help", ""):
            result = await run_case(previous, content, ready=False)
            assert result == {"text_messages": 1, "image_messages": 0, "calculations_started": 0}
            results.append({"source": "before", "content": content, **result})
    for content, ready, enabled, expected in (
        ("help", False, True, (1, 0, 0)),
        ("", False, True, (1, 1, 1)),
        ("", True, True, (0, 1, 1)),
        ("20250", False, True, (1, 0, 0)),
        ("", False, False, (1, 0, 0)),
    ):
        result = await run_case(ROOT / "main.py", content, ready, enabled)
        assert tuple(result.values()) == expected, result
        results.append({"source": "after", "content": content, **result})
    for content, ready, enabled, expected in (
        ("help", False, True, (1, 0, 0)),
        ("帮助", False, True, (1, 0, 0)),
        ("", False, True, (1, 1, 1)),
        ("", True, True, (0, 1, 1)),
        ("20250", False, True, (1, 0, 0)),
        ("help 北京", False, True, (1, 0, 0)),
        ("", False, False, (1, 0, 0)),
    ):
        result = await run_case(ROOT / "main.py", content, ready, enabled, "ziwei_chart")
        assert tuple(result.values()) == expected, result
        results.append(
            {
                "source": "ziwei",
                "handler": "ziwei_chart",
                "content": content,
                "ready": ready,
                "enabled": enabled,
                **result,
            }
        )
    return results


def main():
    REFERENCE.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for name, source in FILES.items():
            path = REFERENCE / name
            if not path.exists():
                response = client.get(
                    "https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.28.1/" + source
                )
                response.raise_for_status()
                path.write_bytes(response.content)
    cases = asyncio.run(verify())
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "astrbot_version": "4.28.1",
        "cases": cases,
        "source_sha256": {
            name: hashlib.sha256((REFERENCE / name).read_bytes()).hexdigest() for name in FILES
        },
        "plugin_sha256": hashlib.sha256((ROOT / "main.py").read_bytes()).hexdigest(),
        "scope": (
            "Cached official AstrBot v4.28.1 scheduling/event/call snapshots "
            "identified by SHA-256; "
            "simulated service and transport; no real QQ send"
        ),
    }
    output = ROOT / "data" / "bot-validation" / "pipeline-4.28.1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {len(cases)} official scheduler cases; old and Zi Wei responses complete.")


if __name__ == "__main__":
    main()
