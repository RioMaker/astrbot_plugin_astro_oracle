"""核对官方 CommandFilter 的别名与 GreedyStr；不启动真实 AstrBot 或消息平台。"""

import ast
import copy
import hashlib
import inspect
import json
import re
import types
import typing
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/astrbot/core/star/filter/command.py"


class Event:
    is_at_or_wake_command = True

    def __init__(self, text):
        self.text = text
        self.extras = {}

    def get_message_str(self):
        return self.text

    def set_extra(self, key, value):
        self.extras[key] = value


def main():
    path = ROOT / "data" / "astrbot-reference" / "command.py"
    if not path.exists():
        response = httpx.get(SOURCE_URL, follow_redirects=True, timeout=30)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    official = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in official.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        and node.name in {"GreedyStr", "unwrap_optional", "CommandFilter"}
    ]
    namespace = {
        "inspect": inspect,
        "re": re,
        "types": types,
        "typing": typing,
        "Any": typing.Any,
        "HandlerFilter": object,
        "AstrBotConfig": dict,
        "AstrMessageEvent": object,
        "StarHandlerMetadata": object,
        "CustomFilter": object,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    plugin = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(node for node in plugin.body if isinstance(node, ast.ClassDef))
    method = copy.deepcopy(
        next(
            node
            for node in cls.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "star_chart"
        )
    )
    decorator = method.decorator_list[0]
    name = ast.literal_eval(decorator.args[0])
    aliases = ast.literal_eval(
        next(item.value for item in decorator.keywords if item.arg == "alias")
    )
    method.decorator_list = []
    method.body = [ast.Pass()]
    declaration = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(declaration, "plugin-signature", "exec"), namespace)
    metadata = types.SimpleNamespace(handler=namespace["star_chart"])
    command = namespace["CommandFilter"](name, alias=aliases, handler_md=metadata)
    inputs = [
        "",
        "help",
        "time 2026-10-10 20:30:00",
        "place New York City",
        "at 2026-10-10 20:30:00 上海",
        "200010100100",
        "20010101",
        "北京",
        "北京 20250102",
        "30.25°N 120.5°E",
        "30.25°N 120.5°E 20250102",
    ]
    cases = []
    for prefix in ("星图", "xingtu", "xt", "star"):
        for content in inputs:
            event = Event(prefix + (" " + content if content else ""))
            assert command.filter(event, {})
            assert event.extras["parsed_params"] == {"content": content}
            cases.append(event.text)
    for text in ("stars", "starfish help", "星轨神谕", "astro_oracle help"):
        assert not command.filter(Event(text), {})
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_file_mtime_utc": datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat(),
        "plugin_sha256": hashlib.sha256((ROOT / "main.py").read_bytes()).hexdigest(),
        "cases": cases,
        "result": f"{len(cases)} alias/argument cases passed; 4 unrelated commands ignored",
        "scope": "Official filter code with minimal import collaborators; no live AstrBot/OneBot",
    }
    output = ROOT / "data" / "bot-validation"
    output.mkdir(parents=True, exist_ok=True)
    (output / "command-contract.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(report["result"])


if __name__ == "__main__":
    main()
