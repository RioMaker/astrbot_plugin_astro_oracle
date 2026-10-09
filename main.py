"""星轨神谕的 AstrBot 指令入口；当前版本提供项目骨架信息。"""

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

VERSION = "0.1.0"


class AstroOraclePlugin(Star):
    """以真实天文状态为基础，逐步建立可复现的研究能力。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.command("星轨神谕", alias={"astro_oracle"})
    async def astro_oracle(self, event: AstrMessageEvent, action: str = "帮助"):
        """查询星轨神谕的帮助、状态或开发路线。"""
        if not self.config.get("enabled", True):
            yield event.plain_result("星轨神谕当前已关闭。")
            return

        action = action.strip().lower()
        aliases = {
            "帮助": "help",
            "状态": "status",
            "路线": "roadmap",
        }
        action = aliases.get(action, action)
        help_text = (
            f"星轨神谕 · Astro Oracle v{VERSION}\n"
            "目标：按时间与地点计算真实天体状态，逐步开展特征提取与验证。\n"
            "当前阶段：项目骨架，天文计算尚未接入。\n\n"
            "/星轨神谕 帮助 — 查看使用说明\n"
            "/星轨神谕 状态 — 查看当前开发状态\n"
            "/星轨神谕 路线 — 查看分阶段计划\n"
            "英文别名：/astro_oracle help | status | roadmap"
        )
        responses = {
            "help": help_text,
            "status": (
                f"星轨神谕 v{VERSION}\n"
                "开发阶段：项目骨架\n"
                "天文计算引擎：待接入\n"
                "恒星目录与太阳系历表：待接入\n"
                "当前仅提供帮助、状态和开发路线查询。"
            ),
            "roadmap": (
                "星轨神谕开发路线\n"
                "1. 建立时间与地点输入、天体状态计算及误差验证。\n"
                "2. 接入恒星目录，提取可复现的天文特征。\n"
                "3. 建立经同意的研究数据采集与质量检查。\n"
                "4. 开展基线比较、随机对照与独立样本验证。\n"
                "5. 根据验证结果扩展日期范围和天体数量。\n"
                "当前已完成项目骨架创建。"
            ),
        }
        response = responses.get(action)
        if response is None:
            response = "暂不支持该操作。\n\n" + help_text
        yield event.plain_result(response)
