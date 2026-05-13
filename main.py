from __future__ import annotations

# pyright: reportMissingImports=false

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .chat_work_balance import ChatWorkBalanceConfig
from .chat_work_balance.resolvers.qq_channel_message_resolver import QQChannelMessageResolver
from .chat_work_balance.services.merged_forward_reader import MergedForwardReader
from .chat_work_balance.services.resource_analysis_service import ResourceAnalysisService

_PLUGIN_NAME = "chat_work_balance"


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
        logger.info(
            _format_observable_log(
                "plugin_init",
                unified_msg_origin="<startup>",
                message_id="<startup>",
                platform="qq_official|qq_official_webhook",
            )
        )

    @filter.platform_adapter_type(
        filter.PlatformAdapterType.QQOFFICIAL
        | filter.PlatformAdapterType.QQOFFICIAL_WEBHOOK
    )
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        message_obj = getattr(event, "message_obj", None)
        message_id = str(getattr(message_obj, "message_id", "")) or "<unknown>"
        unified_msg_origin = str(getattr(event, "unified_msg_origin", "")) or "<unknown>"
        platform = _resolve_platform(unified_msg_origin)
        message_chain = getattr(message_obj, "message", None) or []
        logger.info(
            _format_observable_log(
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
            for chunk_index, chunk in enumerate(resolved_message.replay_plan.chunks):
                logger.info(
                    _format_observable_log(
                        "chunk_replayed",
                        unified_msg_origin=unified_msg_origin,
                        message_id=message_id,
                        platform=platform,
                        chunk_index=str(chunk_index),
                        chunk_intent=chunk.intent,
                        source_indexes=_format_source_indexes(chunk.source_indexes),
                        chunk_summary=_shorten(chunk.summary),
                    )
                )
                yield event.chain_result(chunk.chain)
            logger.info(
                _format_observable_log(
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
                _format_observable_log(
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


def _format_observable_log(
    stage: str,
    *,
    unified_msg_origin: str,
    message_id: str,
    platform: str,
    **fields: str,
) -> str:
    parts = [
        f"plugin={_PLUGIN_NAME}",
        f"stage={stage}",
        f"platform={platform}",
        f"unified_msg_origin={unified_msg_origin}",
        f"message_id={message_id}",
    ]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    return " ".join(parts)


def _resolve_platform(unified_msg_origin: str) -> str:
    if not unified_msg_origin:
        return "<unknown>"
    return unified_msg_origin.split(":", 1)[0] or "<unknown>"


def _format_source_indexes(source_indexes: tuple[int, ...]) -> str:
    return ",".join(str(index) for index in source_indexes) or "<none>"


def _shorten(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."
