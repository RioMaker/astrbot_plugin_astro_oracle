"""以官方 AstrBot 4.28.1 代码核对紫微工具契约；不调用 LLM、QQ 或真实排盘。"""

import __future__

import argparse
import ast
import asyncio
import copy
import hashlib
import importlib
import inspect
import json
import re
import sys
import traceback
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from importlib import metadata
from pathlib import Path

import httpx

from local_core.bot_commands import ChartSettings, parse_request
from local_core.resources import ResourceDownloadError

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "astrbot-reference"
BASE_URL = "https://raw.githubusercontent.com/AstrBotDevs/AstrBot/v4.28.1/"
SOURCES = {
    "filter-v4.28.1.py": (
        "astrbot/api/event/filter/__init__.py",
        "a564263fa78b714a3977292ca2cfa55bf11b417cfdec7cfd16579cf38de56594",
    ),
    "llm-register-v4.28.1.py": (
        "astrbot/core/star/register/star_handler.py",
        "8eeeb59901d9944f10e326bfa10f76eee0629c3f380ed1fb7c5c47b3e50dc266",
    ),
    "func-tool-manager-v4.28.1.py": (
        "astrbot/core/provider/func_tool_manager.py",
        "bef0154d4bd50b924cd9e1be82426d67bfc1f410c2f725d5812d9d936316eab4",
    ),
    "astr-agent-tool-exec-v4.28.1.py": (
        "astrbot/core/astr_agent_tool_exec.py",
        "eaaf96123eb6f09e7685ff8c9c4c82a5954c7db3c93806550b866e554c7f2565",
    ),
    "context-v4.28.1.py": (
        "astrbot/core/star/context.py",
        "a9a2772080b463583af2c3082b4c13e3612ebd9fda0d234147be462394a1ba2e",
    ),
    "event-v4.28.1.py": (
        "astrbot/core/platform/astr_message_event.py",
        "1c51db0b7e78e8cf6c8aa0f64c621d87e2af72a21fee0ff1524b68e6b5850954",
    ),
    "message-session-v4.28.1.py": (
        "astrbot/core/platform/message_session.py",
        "86563844e9a0322cfaf475fda4f3699017c6747232c065298264b541af5a9ca3",
    ),
    "message-type-v4.28.1.py": (
        "astrbot/core/platform/message_type.py",
        "b869f928df01ffb6fd1799c54e9bcb0174655f1d951473f726626337c702edf8",
    ),
    "qqofficial-adapter-v4.28.1.py": (
        "astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py",
        "35dc19e1207d4027023d52df100bf421327a7d2e541e20a221ecfabfd9437e61",
    ),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_sources():
    REFERENCE.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for filename, (source, digest) in SOURCES.items():
            path = REFERENCE / filename
            if not path.exists():
                response = client.get(BASE_URL + source)
                response.raise_for_status()
                if hashlib.sha256(response.content).hexdigest() != digest:
                    raise ValueError(f"Official snapshot hash mismatch: {filename}")
                path.write_bytes(response.content)
            if sha256(path) != digest:
                raise ValueError(f"Cached official snapshot hash mismatch: {filename}")


def tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def compile_nodes(nodes, path, namespace):
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(
        compile(module, str(path), "exec", flags=__future__.annotations.compiler_flag),
        namespace,
    )


def load_function(path, name, namespace, class_name=None, keep_decorators=False):
    scope = tree(path)
    if class_name:
        scope = next(
            node
            for node in scope.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    node = copy.deepcopy(
        next(
            node
            for node in scope.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        )
    )
    if not keep_decorators:
        node.decorator_list = []
    compile_nodes([node], path, namespace)
    return namespace[name]


class Chain:
    """Only message/result storage is simulated; event methods remain official source."""

    def __init__(self, chain=None, **kwargs):
        self.chain = chain or []
        self.stopped = False

    def message(self, text):
        self.chain.append(types.SimpleNamespace(text=text))
        return self

    def stop_event(self):
        self.stopped = True
        return self

    def is_stopped(self):
        return self.stopped


@dataclass
class ToolContainer:
    """Structural FunctionTool collaborator; schema construction is the official method."""

    name: str
    parameters: dict
    description: str
    handler: object

    async def call(self, context, **kwargs):
        raise NotImplementedError


@dataclass
class TextContainer:
    type: str
    text: str


@dataclass
class ResultContainer:
    content: list


class Registry:
    def __init__(self):
        self.items = {}

    def get_handler_by_full_name(self, name):
        return self.items.get(name)

    def append(self, item):
        self.items[item.handler_full_name] = item


def prepare_namespace(parser):
    from local_core.ziwei_invocation import capture_qq_caller

    module = types.ModuleType("ziwei_tool_contract_isolation")
    sys.modules[module.__name__] = module
    namespace = module.__dict__
    namespace.update(
        {
            "asyncio": asyncio,
            "copy": copy,
            "dataclass": dataclass,
            "field": field,
            "Enum": Enum,
            "inspect": inspect,
            "json": json,
            "re": re,
            "traceback": traceback,
            "docstring_parser": parser,
            "datetime": datetime,
            "timezone": timezone,
            "ChartSettings": ChartSettings,
            "parse_request": parse_request,
            "ResourceDownloadError": ResourceDownloadError,
            "capture_qq_caller": capture_qq_caller,
            "MessageChain": Chain,
            "MessageEventResult": Chain,
            "CommandResult": Chain,
            "FunctionTool": ToolContainer,
            "FuncTool": ToolContainer,
            "StarHandlerMetadata": types.SimpleNamespace,
            "star_handlers_registry": Registry(),
            "EventType": types.SimpleNamespace(OnCallingFuncToolEvent="OnCallingFuncToolEvent"),
            "Plain": lambda text: types.SimpleNamespace(text=text),
            "Image": types.SimpleNamespace(fromBytes=lambda png: types.SimpleNamespace(png=png)),
            "mcp": types.SimpleNamespace(
                types=types.SimpleNamespace(
                    TextContent=TextContainer, CallToolResult=ResultContainer
                )
            ),
            "logger": types.SimpleNamespace(
                info=lambda *args, **kwargs: None,
                warning=lambda *args, **kwargs: None,
                error=lambda *args, **kwargs: None,
                exception=lambda *args, **kwargs: None,
            ),
        }
    )
    for filename, class_name in (
        ("message-type-v4.28.1.py", "MessageType"),
        ("message-session-v4.28.1.py", "MessageSession"),
    ):
        path = REFERENCE / filename
        node = next(
            node
            for node in tree(path).body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        compile_nodes([node], path, namespace)
    namespace["MessageSesion"] = namespace["MessageSession"]
    event_path = REFERENCE / "event-v4.28.1.py"
    event_methods = {
        name: load_function(event_path, name, namespace, "AstrMessageEvent")
        for name in (
            "set_result",
            "get_result",
            "stop_event",
            "is_stopped",
            "get_platform_name",
            "get_platform_id",
            "get_group_id",
            "get_sender_id",
        )
    }
    namespace["AstrMessageEvent"] = type("OfficialEventMethods", (), event_methods)
    manager_path = REFERENCE / "func-tool-manager-v4.28.1.py"
    constants = [
        node
        for node in tree(manager_path).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id in {"SUPPORTED_TYPES", "PY_TO_JSON_TYPE"}
            for target in node.targets
        )
    ]
    compile_nodes(constants, manager_path, namespace)
    manager_methods = {
        name: load_function(manager_path, name, namespace, "FunctionToolManager")
        for name in ("spec_to_func", "add_func", "remove_func")
    }
    manager = type("OfficialToolManagerMethods", (), manager_methods)()
    manager.func_list = []
    namespace["llm_tools"] = manager
    registration = REFERENCE / "llm-register-v4.28.1.py"
    for name in ("get_handler_full_name", "get_handler_or_create", "register_llm_tool"):
        load_function(registration, name, namespace)
    load_function(REFERENCE / "astr-agent-tool-exec-v4.28.1.py", "call_local_llm_tool", namespace)
    execute = load_function(
        REFERENCE / "astr-agent-tool-exec-v4.28.1.py",
        "_execute_local",
        namespace,
        "FunctionToolExecutor",
        keep_decorators=True,
    )
    namespace["executor"] = type("OfficialExecutorMethod", (), {"_execute_local": execute})
    context_send = load_function(
        REFERENCE / "context-v4.28.1.py", "send_message", namespace, "Context"
    )
    namespace["context_type"] = type(
        "OfficialSendMessageMethod", (), {"send_message": context_send}
    )
    for name in ("ziwei_help", "ziwei_error_text"):
        load_function(ROOT / "main.py", name, namespace)
    for name in ("generate_ziwei_chart", "_finish_ziwei_record", "_run_ziwei"):
        load_function(ROOT / "main.py", name, namespace, "AstroOraclePlugin")
    return namespace


def verify_registration(namespace):
    aliases = [
        alias
        for node in tree(REFERENCE / "filter-v4.28.1.py").body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname == "llm_tool"
    ]
    assert len(aliases) == 1 and aliases[0].name == "register_llm_tool"
    plugin_class = next(
        node for node in tree(ROOT / "main.py").body if isinstance(node, ast.ClassDef)
    )
    method = next(
        node for node in plugin_class.body if getattr(node, "name", "") == "generate_ziwei_chart"
    )
    decorator = method.decorator_list[0]
    assert isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "llm_tool"
    name = ast.literal_eval(next(item.value for item in decorator.keywords if item.arg == "name"))
    assert name == "generate_ziwei_chart"
    handler = namespace["generate_ziwei_chart"]
    assert inspect.iscoroutinefunction(handler) and not inspect.isasyncgenfunction(handler)
    assert not any(isinstance(node, (ast.Yield, ast.YieldFrom)) for node in ast.walk(method))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "stop_event"
        for node in ast.walk(method)
    )
    registered = namespace["register_llm_tool"](name=name)(handler)
    assert registered is handler
    tools = namespace["llm_tools"].func_list
    assert len(tools) == 1 and tools[0].handler is handler
    tool = tools[0]
    assert set(tool.parameters["properties"]) == {"query"}, tool.parameters
    query = tool.parameters["properties"]["query"]
    assert query["type"] == "string"
    assert "20261014200000" in query["description"]
    assert "tz=UTC+08:00" in query["description"]
    assert "空字符串" in query["description"]
    assert "required" not in tool.parameters
    assert inspect.signature(handler).parameters["query"].default is None
    return tool


async def run_case(
    namespace,
    registered_tool,
    name,
    arguments,
    *,
    config=None,
    platform="aiocqhttp",
    group="synthetic-group",
    transport="ok",
    service="ok",
    mutate_event=False,
):
    event = namespace["AstrMessageEvent"]()
    event.platform_meta = types.SimpleNamespace(name=platform, id="synthetic-onebot")
    event.message_obj = types.SimpleNamespace(
        group_id=group,
        sender=types.SimpleNamespace(user_id="synthetic-user"),
        message_id="synthetic-message",
    )
    event.unified_msg_origin = "synthetic-onebot:GroupMessage:synthetic-group"
    event._result, event._force_stopped = None, False
    sent, calculations, starts, finishes = [], [], [], []

    async def send_by_session(session, chain):
        if transport == "raises":
            raise RuntimeError("isolated transport failure")
        sent.append((str(session), chain))

    adapter = types.SimpleNamespace(
        meta=lambda: types.SimpleNamespace(
            id="unmatched" if transport == "unmatched" else "synthetic-onebot",
            name=platform,
        ),
        send_by_session=send_by_session,
    )
    context = namespace["context_type"]()
    context.platform_manager = types.SimpleNamespace(platform_insts=[adapter])
    context.get_config = lambda **kwargs: {}

    async def generate(request, settings, now):
        calculations.append(request)
        await asyncio.sleep(0)
        if mutate_event:
            event.unified_msg_origin = "changed:GroupMessage:changed"
            event.platform_meta.id = "changed"
            event.message_obj.group_id = "changed"
            event.message_obj.sender.user_id = "changed"
        if service == "invalid":
            raise ValueError("isolated calculation validation failure")
        if service == "resource":
            raise ResourceDownloadError("isolated public resource failure")
        if service == "cancelled":
            raise asyncio.CancelledError
        return types.SimpleNamespace(
            png=b"isolated message routing bytes; not an astronomy PNG",
            metadata={"validation": "simulated service; no astronomical claims"},
        )

    async def start(*args):
        starts.append(args)
        return 1

    async def finish(*args):
        finishes.append(args)

    plugin = types.SimpleNamespace(
        config={"enabled": True, "enable_ziwei_llm_tool": True, **(config or {})},
        context=context,
        _charts=types.SimpleNamespace(ready=False, generate_ziwei_result=generate),
        _ziwei_records=types.SimpleNamespace(start=start, finish=finish),
    )
    for helper in ("_finish_ziwei_record", "_run_ziwei"):
        setattr(plugin, helper, namespace[helper].__get__(plugin))
    tool = copy.copy(registered_tool)
    tool.handler = namespace["generate_ziwei_chart"].__get__(plugin)
    run_context = types.SimpleNamespace(
        context=types.SimpleNamespace(event=event), tool_call_timeout=10
    )
    cancelled = False
    results = []
    try:
        async for result in namespace["executor"]._execute_local(tool, run_context, **arguments):
            results.append(result)
    except asyncio.CancelledError:
        cancelled = True
    assert not event.is_stopped(), name
    assert event.get_result() is None, name
    if cancelled:
        assert service == "cancelled" and not results and not sent
        assert len(finishes) == 1 and finishes[0][1] == "cancelled"
        status = "cancelled"
    else:
        assert len(results) == 1 and len(results[0].content) == 1, name
        assert results[0].content[0].type == "text"
        text = results[0].content[0].text
        assert isinstance(text, str)
        if arguments.get("query") == "help":
            assert "/紫薇星图" in text and not calculations and not starts and not sent
            status = "help"
        else:
            outcome = json.loads(text)
            status = outcome["status"]
            expected = (
                "disabled"
                if config
                and (config.get("enabled") is False or config.get("enable_ziwei_llm_tool") is False)
                else "invalid_request"
                if not isinstance(arguments.get("query"), str) or arguments.get("query") == "20250"
                else "failed"
                if service != "ok"
                else "send_failed"
                if transport != "ok"
                else "sent"
            )
            assert status == expected, (name, outcome)
            if status in {"disabled", "invalid_request"}:
                assert not calculations and not starts and not finishes and not sent
            else:
                assert len(calculations) == 1
                should_record = (
                    bool(group)
                    and platform in {"aiocqhttp", "qq_official"}
                    and bool(arguments.get("query"))
                    and plugin.config.get("record_ziwei_queries", True)
                )
                assert len(starts) == len(finishes) == int(should_record), name
                assert outcome["recorded"] == should_record
                if starts:
                    caller = starts[0][0]
                    assert (caller.platform_id, caller.group_id, caller.user_id) == (
                        "synthetic-onebot",
                        "synthetic-group",
                        "synthetic-user",
                    )
                    assert starts[0][1] == "llm" and finishes[0][1] == status
                assert len(sent) == int(status == "sent"), name
                if sent:
                    assert sent[0][0] == "synthetic-onebot:GroupMessage:synthetic-group"
                    assert len(sent[0][1].chain) == 1 and hasattr(sent[0][1].chain[0], "png")
    return {
        "name": name,
        "arguments": arguments,
        "status": status,
        "event_stopped": event.is_stopped(),
        "calculations": len(calculations),
        "sent_image_components": len(sent),
        "records_started": len(starts),
        "records_finished": len(finishes),
        "official_executor_text_results": len(results),
    }


async def verify(namespace, tool):
    cases = [
        ("explicit_date_frozen_identity_and_route", {"query": "20000102"}, {"mutate_event": True}),
        ("empty_query_current_no_record", {"query": ""}, {}),
        ("omitted_query_rejected", {}, {}),
        ("null_query_rejected", {"query": None}, {}),
        ("number_query_rejected", {"query": 20000102}, {}),
        ("invalid_date_rejected", {"query": "20250"}, {}),
        ("help_keeps_event_active", {"query": "help"}, {}),
        ("global_disabled", {"query": "20000102"}, {"config": {"enabled": False}}),
        ("tool_disabled", {"query": "20000102"}, {"config": {"enable_ziwei_llm_tool": False}}),
        ("record_disabled", {"query": "20000102"}, {"config": {"record_ziwei_queries": False}}),
        ("non_qq_no_record", {"query": "20000102"}, {"platform": "telegram"}),
        ("private_qq_no_record", {"query": "20000102"}, {"group": ""}),
        ("transport_exception_recorded", {"query": "20000102"}, {"transport": "raises"}),
        ("unmatched_transport_recorded", {"query": "20000102"}, {"transport": "unmatched"}),
        ("resource_failure_recorded", {"query": "20000102"}, {"service": "resource"}),
        ("calculation_failure_recorded", {"query": "20000102"}, {"service": "invalid"}),
        ("cancellation_recorded", {"query": "20000102"}, {"service": "cancelled"}),
    ]
    return [await run_case(namespace, tool, name, args, **options) for name, args, options in cases]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--dependency-path",
        type=Path,
        help="可选：含 docstring_parser 的 AstrBot/Python site-packages；不会修改依赖",
    )
    args = cli.parse_args()
    if args.dependency_path:
        sys.path.append(str(args.dependency_path.resolve()))
    try:
        parser = importlib.import_module("docstring_parser")
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "需要 AstrBot 的 docstring-parser>=0.16；在 AstrBot 环境运行，"
            "或用 --dependency-path 指定已有 site-packages。"
        ) from exc
    prepare_sources()
    namespace = prepare_namespace(parser)
    tool = verify_registration(namespace)
    cases = asyncio.run(verify(namespace, tool))
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "astrbot_version": "4.28.1",
        "result": "passed",
        "schema": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
        "schema_required_note": (
            "Official decorator/spec_to_func omit required; "
            "plugin rejects omitted/null/non-string query. Explicit empty string requests now."
        ),
        "qqofficial_note": (
            "Context.send_message docstring says qq_official is unsupported, but the same "
            "version's adapter implements send_by_session for QQ groups and guild channels. "
            "Neither is live-tested here. Both kinds use GROUP_MESSAGE and nonempty group_id; "
            "raw_message.group_openid identifies a QQ group, while channel_id identifies a channel."
        ),
        "sources": {
            filename: {"url": BASE_URL + source, "sha256": digest}
            for filename, (source, digest) in SOURCES.items()
        },
        "plugin_sha256": {
            name: sha256(ROOT / name)
            for name in (
                "main.py",
                "local_core/bot_commands.py",
                "local_core/ziwei_invocation.py",
                "local_core/ziwei_records.py",
            )
        },
        "docstring_parser": {
            "version": metadata.version("docstring-parser"),
            "module_path": parser.__file__,
        },
        "executed_official_functions": [
            "get_handler_full_name",
            "get_handler_or_create",
            "register_llm_tool",
            "FunctionToolManager.spec_to_func/add_func/remove_func",
            "FunctionToolExecutor._execute_local",
            "call_local_llm_tool",
            "Context.send_message",
            "MessageSession.from_str",
            "AstrMessageEvent identity/result/stop methods",
        ],
        "checks": {
            "registration_and_multiline_schema": 1,
            "official_executor_cases": len(cases),
            "events_kept_active": len(cases),
        },
        "cases": cases,
        "scope": (
            "Official version-pinned AST function bodies are executed unchanged; "
            "registry metadata, "
            "FunctionTool/MCP containers, images, service, storage and platform transport are "
            "isolated collaborators. Synthetic date/identity cases only. No real astronomy PNG, "
            "SQLite record, LLM request, QQ send or full AstrBot loading is tested. "
            "The official QQ adapter source is recorded to qualify its stale Context docstring, "
            "not to assert live transport support. True means a platform matched and its send "
            "coroutine returned, not a QQ delivery receipt."
        ),
    }
    output = ROOT / "data" / "bot-validation" / "ziwei-tool-contract-4.28.1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(
        f"PASS: official multiline query schema; {len(cases)} executor cases; "
        f"all events continue. Report: {output}"
    )


if __name__ == "__main__":
    main()
