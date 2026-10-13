"""星轨神谕的 AstrBot 入口；星图与紫微星图使用独立指令。"""

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

PLUGIN_NAME = "astrbot_plugin_astro_oracle"


def ziwei_help(settings):
    return (
        "紫微星图：同一时间地点的传统静态命盘与真实天体位置对照。\n"
        "/紫微星图 — 当前时刻与默认地点\n"
        "/紫微星图 北京 20261012200000 — 指定公历时间与地点\n"
        "/紫微星图 30.25°N 120.5°E 20250102 — 指定经纬度\n"
        "/紫微星图 help 或 /紫微星图 帮助 — 查看帮助\n"
        "时间与地点可交换顺序；支持年、年月、日期以及具体到秒的紧凑时间。\n"
        f"默认地点：{settings.default_place}；缺时分秒按 {settings.default_time} 补齐。\n"
        f"城市采用当地时区，经纬度默认 {settings.coordinate_timezone}；可在末尾加 tz=...。\n"
        "传统安星历法验收范围为 1900–2100 年；图中分别标明传统宫位与实体天文坐标。"
    )


def ziwei_error_text(error):
    """共用参数解析器的错误文案只引导到当前紫微指令。"""
    return f"{str(error).replace('/星图', '/紫微星图')}\n使用 /紫微星图 help 查看帮助。"


class AstroOraclePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        migrate_default_time(config)
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        self._charts = ChartService(data_dir)

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

    @filter.command("紫微星图", alias=set())
    async def ziwei_chart(self, event: AstrMessageEvent, content: GreedyStr):
        """传统命盘与真实天体位置对照；help/帮助及时间地点参数。"""
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
        if not self._charts.ready:
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
        try:
            png = await self._charts.generate_ziwei(request, settings, now)
        except ResourceDownloadError as exc:
            logger.exception("紫微星图公共资源下载失败")
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
            await self.context.send_message(origin, MessageChain([Plain(ziwei_error_text(exc))]))
            return
        except Exception:
            logger.exception("紫微星图资源准备或图片生成失败")
            await self.context.send_message(
                origin,
                MessageChain(
                    [Plain("紫微星图生成失败，请检查 AstrBot 日志中的资源或渲染错误后重试。")]
                ),
            )
            return
        await self.context.send_message(origin, MessageChain([Image.fromBytes(png)]))

    async def terminate(self):
        await self._charts.close()
