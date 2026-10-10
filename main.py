"""星轨神谕的 AstrBot 入口；现阶段仅提供星图指令。"""

from datetime import datetime, timezone
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .local_core.bot_commands import ChartSettings, help_text, parse_request
from .local_core.bot_service import ChartService

PLUGIN_NAME = "astrbot_plugin_astro_oracle"


class AstroOraclePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        self._charts = ChartService(data_dir)

    @filter.command("星图", alias={"xingtu", "xt", "star"})
    async def star_chart(self, event: AstrMessageEvent, content: GreedyStr):
        """当前星图；help/帮助、time/时间、place/地点、at/时地。"""
        # GreedyStr 接收全部参数，也允许空字符串；不能为它添加普通字符串默认值。
        # 在第一次 yield/await 前固定路由、输入、配置与请求时刻。
        origin = str(event.unified_msg_origin)
        now = datetime.now(timezone.utc)
        event.stop_event()
        if not self.config.get("enabled", True):
            yield event.plain_result("星图功能当前已关闭。")
            return
        try:
            settings = ChartSettings.from_mapping(self.config)
            request = parse_request(str(content))
        except ValueError as exc:
            yield event.plain_result(f"{exc}\n使用 /星图 help 查看帮助。")
            return
        if request.action == "help":
            yield event.plain_result(help_text(settings))
            return
        if not self._charts.ready:
            yield event.plain_result("正在准备星图资源。首次使用需下载并校验公共天文数据，请稍候。")
        try:
            png = await self._charts.generate(request, settings, now)
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

    async def terminate(self):
        await self._charts.close()
