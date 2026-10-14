"""星轨神谕的 AstrBot 入口；星图与紫微星图使用独立指令。"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .local_core.bot_commands import ChartSettings, help_text, migrate_default_time, parse_request
from .local_core.bot_service import ChartService
from .local_core.resources import ResourceDownloadError
from .local_core.ziwei_invocation import capture_qq_caller
from .local_core.ziwei_records import ZiweiRecordStore

PLUGIN_NAME = "astrbot_plugin_astro_oracle"


def ziwei_help(settings):
    return (
        "紫微星图：同一时间地点的传统静态命盘与真实天体位置对照。\n"
        "/紫薇星图 与 /紫微星图 完全等效 — 当前时刻与默认地点\n"
        "/紫薇星图 20261014200000 — 只指定时间，使用默认地点\n"
        "/紫薇星图 20261014 — 只指定日期，补齐默认时间\n"
        "/紫薇星图 北京 20261012200000 — 指定公历时间与地点\n"
        "/紫微星图 30.25°N 120.5°E 20250102 — 指定经纬度\n"
        "/紫薇星图 help 或 /紫微星图 帮助 — 查看帮助\n"
        "时间与地点可交换顺序；支持年、年月、日期以及具体到秒的紧凑时间。\n"
        f"默认地点：{settings.default_place}；缺时分秒按 {settings.default_time} 补齐。\n"
        "未更改默认地点配置时，省略地点即采用北京与北京时间（Asia/Shanghai）。\n"
        f"城市采用当地时区，经纬度默认 {settings.coordinate_timezone}；可在末尾加 tz=...。\n"
        "传统安星历法验收范围为 1900–2100 年；图中分别标明传统宫位与实体天文坐标。"
    )


def ziwei_error_text(error):
    """共用参数解析器的错误文案只引导到当前紫微指令。"""
    return (
        f"{str(error).replace('/星图', '/紫微星图')}\n"
        "使用 /紫薇星图 help 或 /紫微星图 help 查看帮助。"
    )


class AstroOraclePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        migrate_default_time(config)
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        self._charts = ChartService(data_dir)
        self._ziwei_records = ZiweiRecordStore(data_dir / "ziwei_calls.sqlite3")

    @filter.command("星图", alias={"xingtu", "xt", "star"})
    async def star_chart(self, event: AstrMessageEvent, content: GreedyStr):
        """当前星图；help/帮助、time/时间、place/地点、at/时地。"""
        # GreedyStr 接收全部参数，也允许空字符串；不能为它添加普通字符串默认值。
        # 在第一次 await 前固定路由、输入、配置与请求时刻。
        origin = str(event.unified_msg_origin)
        now = datetime.now(timezone.utc)
        event.stop_event()
        if not self.config.get("enabled", True):
            await self.context.send_message(origin, MessageChain([Plain("星图功能当前已关闭。")]))
            return
        try:
            settings = ChartSettings.from_mapping(self.config)
            request = parse_request(str(content))
        except ValueError as exc:
            await self.context.send_message(
                origin, MessageChain([Plain(f"{exc}\n使用 /星图 help 查看帮助。")])
            )
            return
        if request.action == "help":
            await self.context.send_message(origin, MessageChain([Plain(help_text(settings))]))
            return
        if not self._charts.ready:
            await self.context.send_message(
                origin,
                MessageChain(
                    [Plain("正在检查并准备星图资源，已完成下载并通过校验的文件会复用，请稍候。")]
                ),
            )
        try:
            png = await self._charts.generate(request, settings, now)
        except ResourceDownloadError as exc:
            logger.exception("星图公共资源下载失败")
            await self.context.send_message(
                origin,
                MessageChain(
                    [
                        Plain(
                            f"{exc}\n请检查运行端网络，或将离线资源包解压到插件数据目录后重试。"
                            "已缓存的完整资源会复用。"
                        )
                    ]
                ),
            )
            return
        except ValueError as exc:
            await self.context.send_message(
                origin, MessageChain([Plain(f"{exc}\n使用 /星图 help 查看帮助。")])
            )
            return
        except Exception:
            logger.exception("星图资源准备或图片生成失败")
            await self.context.send_message(
                origin,
                MessageChain(
                    [Plain("星图生成失败，请检查 AstrBot 日志中的资源或渲染错误后重试。")]
                ),
            )
            return
        # 图片仅在内存中生成；通过固定的会话路由发送，避免异步期间读取共享 event。
        await self.context.send_message(origin, MessageChain([Image.fromBytes(png)]))

    @filter.command("紫微星图", alias={"紫薇星图"})
    async def ziwei_chart(self, event: AstrMessageEvent, content: GreedyStr):
        """紫微星图／紫薇星图：传统命盘与真实天体对照；help/帮助及时间地点。"""
        origin = str(event.unified_msg_origin)
        now = datetime.now(timezone.utc)
        event.stop_event()
        if not self.config.get("enabled", True):
            await self.context.send_message(
                origin, MessageChain([Plain("紫微星图功能当前已关闭。")])
            )
            return
        try:
            settings = ChartSettings.from_mapping(self.config)
            request = parse_request(str(content))
        except ValueError as exc:
            await self.context.send_message(origin, MessageChain([Plain(ziwei_error_text(exc))]))
            return
        if request.action == "help":
            await self.context.send_message(origin, MessageChain([Plain(ziwei_help(settings))]))
            return
        caller = capture_qq_caller(event)
        record_enabled = bool(self.config.get("record_ziwei_queries", True))
        outcome = await self._run_ziwei(
            origin, now, request, settings, caller, "command", record_enabled
        )
        if outcome["status"] != "sent":
            await self.context.send_message(origin, MessageChain([Plain(outcome["message"])]))
        if outcome.get("record_warning"):
            await self.context.send_message(
                origin, MessageChain([Plain(outcome["record_warning"])])
            )

    @filter.llm_tool(name="generate_ziwei_chart")
    async def generate_ziwei_chart(self, event: AstrMessageEvent, query: str | None = None) -> str:
        """根据用户要求生成紫薇／紫微命盘与真实天球对照图，直接发送到当前会话。

        仅在用户请求排盘时使用。日期采用用户明确提供的公历日期，不猜测生日；
        未指定地点时使用配置中的默认地点（出厂为北京、北京时间）。
        用户要求当前时刻时 query 可为空。图片发出后无需再次调用或重复发图。

        Args:
            query(string): 时间与可选地点，不含指令前缀，例如 20261014200000 或 北京 20261014。
                支持 2026-10-14 20:00:00，末尾可加 tz=UTC+08:00。
                缺时分秒按配置补齐，出厂默认 08:00:00；查询当前时刻时明确传空字符串。
        """
        origin = str(event.unified_msg_origin)
        now = datetime.now(timezone.utc)
        if not self.config.get("enabled", True) or not self.config.get(
            "enable_ziwei_llm_tool", True
        ):
            return json.dumps(
                {"status": "disabled", "message": "紫微星图 AI 工具当前已关闭。"},
                ensure_ascii=False,
            )
        try:
            settings = ChartSettings.from_mapping(self.config)
            request = parse_request(query)
        except ValueError as exc:
            return json.dumps(
                {"status": "invalid_request", "message": ziwei_error_text(exc)},
                ensure_ascii=False,
            )
        if request.action == "help":
            return ziwei_help(settings)
        caller = capture_qq_caller(event)
        record_enabled = bool(self.config.get("record_ziwei_queries", True))
        outcome = await self._run_ziwei(
            origin, now, request, settings, caller, "llm", record_enabled
        )
        return json.dumps(outcome, ensure_ascii=False, allow_nan=False)

    async def _finish_ziwei_record(self, record_id, status, result=None, error_code=None):
        if record_id is None:
            return False
        writing = asyncio.create_task(
            self._ziwei_records.finish(record_id, status, result, error_code)
        )
        try:
            await asyncio.shield(writing)
            return True
        except asyncio.CancelledError:
            # 图片可能已经发出，不能取消排队中的终态写入或改写为未发送。
            try:
                await asyncio.shield(writing)
            except Exception as exc:
                logger.error(f"紫微调用记录更新失败：{type(exc).__name__}")
            raise
        except Exception as exc:
            logger.error(f"紫微调用记录更新失败：{type(exc).__name__}")
            return False

    async def _run_ziwei(self, origin, now, request, settings, caller, source, record_enabled):
        record_id, warning = None, None
        if record_enabled and caller is not None and request.time_text is not None:
            try:
                starting = asyncio.create_task(
                    self._ziwei_records.start(caller, source, request, settings, now)
                )
                try:
                    record_id = await asyncio.shield(starting)
                except asyncio.CancelledError:
                    # SQLite 线程可能继续插入；取得 ID 后收尾，避免留下悬挂 pending。
                    try:
                        record_id = await asyncio.shield(starting)
                    except Exception as exc:
                        logger.error(f"紫微调用记录创建失败：{type(exc).__name__}")
                    else:
                        await asyncio.shield(
                            self._finish_ziwei_record(record_id, "cancelled", None, "cancelled")
                        )
                    raise
            except Exception as exc:
                logger.error(f"紫微调用记录创建失败：{type(exc).__name__}")
                warning = "本次调用记录未能保存，请管理员检查插件数据目录。"
        result = None
        try:
            try:
                if not self._charts.ready and source == "command":
                    await self.context.send_message(
                        origin,
                        MessageChain(
                            [
                                Plain(
                                    "正在检查并准备紫微星图资源，已下载并通过校验的公共文件会复用，请稍候。"
                                )
                            ]
                        ),
                    )
                result = await self._charts.generate_ziwei_result(request, settings, now)
            except ResourceDownloadError as exc:
                logger.exception("紫微星图公共资源下载失败")
                outcome = {
                    "status": "failed",
                    "error_code": "resource_unavailable",
                    "message": (
                        f"{exc}\n请检查运行端网络，或将离线资源包解压到插件数据目录后重试。"
                        "已缓存的完整资源会复用。"
                    ),
                }
            except ValueError as exc:
                outcome = {
                    "status": "failed",
                    "error_code": "invalid_request",
                    "message": ziwei_error_text(exc),
                }
            except Exception:
                logger.exception("紫微星图资源准备或图片生成失败")
                outcome = {
                    "status": "failed",
                    "error_code": "generation_failed",
                    "message": "紫微星图生成失败，请检查 AstrBot 日志中的资源或渲染错误后重试。",
                }
            else:
                try:
                    sent = await self.context.send_message(
                        origin, MessageChain([Image.fromBytes(result.png)])
                    )
                    if sent is False:
                        raise RuntimeError("message transport returned false")
                except Exception:
                    logger.exception("紫微星图图片发送失败")
                    outcome = {
                        "status": "send_failed",
                        "error_code": "send_failed",
                        "message": "紫微星图已生成，但图片发送失败，请稍后重试。",
                    }
                else:
                    outcome = {"status": "sent", "message": "紫微星图已发送到当前会话。"}
                outcome["chart"] = result.metadata
        except asyncio.CancelledError:
            await asyncio.shield(
                self._finish_ziwei_record(
                    record_id, "cancelled", result.metadata if result else None, "cancelled"
                )
            )
            raise
        recorded = await self._finish_ziwei_record(
            record_id,
            outcome["status"],
            result.metadata if result else None,
            outcome.get("error_code"),
        )
        outcome["recorded"] = recorded
        if record_id and not recorded:
            warning = "本次调用记录状态未能更新，请管理员检查插件数据目录。"
        if warning:
            outcome["record_warning"] = warning
        return outcome

    async def terminate(self):
        await self._charts.close()
