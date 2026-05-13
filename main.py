from __future__ import annotations

# pyright: reportMissingImports=false

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .chat_work_balance import ChatWorkBalanceConfig
from .chat_work_balance.resolvers.qq_channel_message_resolver import QQChannelMessageResolver
from .chat_work_balance.services.merged_forward_reader import MergedForwardReader
from .chat_work_balance.services.resource_analysis_service import ResourceAnalysisService


@register(
    "chat_work_balance",
    "xuemufan",
    "QQ Official message resolver skeleton for replay-oriented diagnostics.",
    "0.0.1",
)
class ChatWorkBalancePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        plugin_config = ChatWorkBalanceConfig.from_astrbot_config(config)
        merged_forward_reader = MergedForwardReader()
        resource_analysis_service = ResourceAnalysisService(
            context=context,
            plugin_config=plugin_config,
        )
        self._resolver = QQChannelMessageResolver(
            merged_forward_reader=merged_forward_reader,
            resource_analysis_service=resource_analysis_service,
        )

    @filter.platform_adapter_type(
        filter.PlatformAdapterType.QQOFFICIAL
        | filter.PlatformAdapterType.QQOFFICIAL_WEBHOOK
    )
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            resolved_message = await self._resolver.resolve(event)
            logger.info(resolved_message.log_summary)
            for chunk in resolved_message.replay_plan.chunks:
                yield event.chain_result(chunk.chain)
            event.stop_event()
        except Exception:
            logger.exception("Failed to resolve QQ Official message.")
            yield event.plain_result("Message resolver is temporarily unavailable.")
            event.stop_event()
