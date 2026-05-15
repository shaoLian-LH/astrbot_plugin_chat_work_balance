from __future__ import annotations

# pyright: reportMissingImports=false

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .chat_work_balance import ChatWorkBalanceConfig
from .chat_work_balance.observability import (
    format_observable_log,
    resolve_platform,
    shorten_text,
)
from .chat_work_balance.resolvers.onebot_message_resolver import OneBotMessageResolver
from .chat_work_balance.services.forward_summary_service import ForwardSummaryService
from .chat_work_balance.services.merged_forward_reader import MergedForwardReader
from .chat_work_balance.services.resource_analysis_service import ResourceAnalysisService


@register(
    "chat_work_balance",
    "slfk",
    "OneBot message resolver for replay-oriented diagnostics.",
    "0.0.1",
)
class ChatWorkBalancePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        plugin_config = ChatWorkBalanceConfig.from_astrbot_config(config)
        merged_forward_reader = MergedForwardReader(
            max_depth=plugin_config.forward_max_depth,
            sample_threshold=plugin_config.forward_sample_threshold,
            sample_head_count=plugin_config.forward_sample_head_count,
            sample_tail_count=plugin_config.forward_sample_tail_count,
        )
        forward_summary_service = ForwardSummaryService(
            context=context,
            plugin_config=plugin_config,
        )
        resource_analysis_service = ResourceAnalysisService(
            context=context,
            plugin_config=plugin_config,
        )
        self._resolver = OneBotMessageResolver(
            merged_forward_reader=merged_forward_reader,
            forward_summary_service=forward_summary_service,
            resource_analysis_service=resource_analysis_service,
        )
        logger.info(
            format_observable_log(
                "plugin_init",
                unified_msg_origin="<startup>",
                message_id="<startup>",
                platform="aiocqhttp",
            )
        )

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        message_obj = getattr(event, "message_obj", None)
        message_id = str(getattr(message_obj, "message_id", "")) or "<unknown>"
        unified_msg_origin = str(getattr(event, "unified_msg_origin", "")) or "<unknown>"
        platform = resolve_platform(unified_msg_origin)
        message_chain = getattr(message_obj, "message", None) or []
        logger.info(
            format_observable_log(
                "message_received",
                unified_msg_origin=unified_msg_origin,
                message_id=message_id,
                platform=platform,
                component_count=str(len(message_chain)),
            )
        )
        try:
            resolved_message = await self._resolver.resolve(event)
            logger.info(resolved_message.log_summary)
            forward_summary_indexes = {
                segment.source_index
                for segment in resolved_message.segments
                if segment.kind == "forward_summary"
            }
            for chunk_index, chunk in enumerate(resolved_message.replay_plan.chunks):
                chunk_fields = {
                    "chunk_index": str(chunk_index),
                    "chunk_intent": chunk.intent,
                    "source_indexes": _format_source_indexes(chunk.source_indexes),
                }
                if any(
                    source_index in forward_summary_indexes
                    for source_index in chunk.source_indexes
                ):
                    chunk_fields["chunk_summary_length"] = str(len(chunk.summary))
                    chunk_fields["chunk_source"] = "forward_summary"
                else:
                    chunk_fields["chunk_summary"] = shorten_text(chunk.summary, 120)
                logger.info(
                    format_observable_log(
                        "chunk_replayed",
                        unified_msg_origin=unified_msg_origin,
                        message_id=message_id,
                        platform=platform,
                        **chunk_fields,
                    )
                )
                yield event.chain_result(chunk.chain)
            logger.info(
                format_observable_log(
                    "message_completed",
                    unified_msg_origin=unified_msg_origin,
                    message_id=message_id,
                    platform=platform,
                    chunk_count=str(len(resolved_message.replay_plan.chunks)),
                    dropped_count=str(len(resolved_message.replay_plan.dropped_segments)),
                )
            )
            event.stop_event()
        except Exception as exc:
            logger.exception(
                format_observable_log(
                    "message_failed",
                    unified_msg_origin=unified_msg_origin,
                    message_id=message_id,
                    platform=platform,
                    failure_stage="entry",
                    error_type=type(exc).__name__,
                )
            )
            yield event.plain_result("Message resolver is temporarily unavailable.")
            event.stop_event()


def _format_source_indexes(source_indexes: tuple[int, ...]) -> str:
    return ",".join(str(index) for index in source_indexes) or "<none>"
