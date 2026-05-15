from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context

from ..config import ChatWorkBalanceConfig
from ..observability import format_source_observable_log, shorten_text
from .provider_utils import extract_completion_text, lookup_chat_provider

_MAX_PROVIDER_ATTEMPTS = 3
_FORWARD_SUMMARY_PROMPT = """你正在为合并转发消息生成可直接回放的中文个人总结。

请阅读下面的 transcript，并严格按以下要求输出：
1. 必须只用中文输出，禁止夹杂英文总结句。
2. 按发送者分组；每个发送者单独整理。
3. 每组都要尽量包含发送者名称；如果 transcript 中有发送者 id，也要一并写出。
4. 每个发送者下按“发言维度”整理核心观点，提炼该发送者最重要的结论、诉求、决定、分歧或风险。
5. 每个发言维度都要保留最关键的原话或短句，作为证据，避免改写掉关键信息。
6. 忽略寒暄、客套、重复表述和无信息量的口头语，除非它们是判断态度或结论的关键证据。
7. 输出要简洁、清晰，结果必须可以直接作为 `forward_summary` 展示给用户。

Transcript:
{transcript}
"""


@dataclass(frozen=True)
class ForwardSummaryResult:
    success: bool
    provider_id: str
    prompt: str
    text: str
    detail: str


class ForwardSummaryService:
    """Summarize merged forward transcripts through the configured text provider."""

    def __init__(self, context: Context, plugin_config: ChatWorkBalanceConfig) -> None:
        self._context = context
        self._plugin_config = plugin_config

    async def summarize_transcript(
        self,
        transcript: str,
        *,
        unified_msg_origin: str,
        source_label: str,
    ) -> ForwardSummaryResult:
        global_config = self._context.get_config(unified_msg_origin)
        provider_id = self._plugin_config.resolve_message_provider_id(global_config)
        prompt = self._build_prompt(transcript)

        provider_lookup = lookup_chat_provider(
            self._context,
            provider_id,
            not_configured_detail="转发总结失败：未配置消息解析模型。",
            not_found_detail=f"转发总结失败：找不到消息解析模型 {provider_id}。",
            invalid_type_detail=f"转发总结失败：消息解析模型 {provider_id} 不是文本对话 provider。",
        )
        if provider_lookup.provider is None:
            return self._configuration_failure(
                detail=provider_lookup.failure_detail,
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )
        provider = provider_lookup.provider

        for attempt in range(1, _MAX_PROVIDER_ATTEMPTS + 1):
            try:
                response = await provider.text_chat(prompt=prompt, image_urls=[])
            except Exception as exc:
                logger.warning(
                    format_source_observable_log(
                        "provider_retry",
                        unified_msg_origin=unified_msg_origin,
                        source_label=source_label,
                        provider_id=provider_id,
                        attempt=str(attempt),
                        max_attempts=str(_MAX_PROVIDER_ATTEMPTS),
                        call_result="exception",
                        error_type=type(exc).__name__,
                    )
                )
                continue

            completion_text = extract_completion_text(response)
            if not completion_text:
                logger.warning(
                    format_source_observable_log(
                        "provider_retry",
                        unified_msg_origin=unified_msg_origin,
                        source_label=source_label,
                        provider_id=provider_id,
                        attempt=str(attempt),
                        max_attempts=str(_MAX_PROVIDER_ATTEMPTS),
                        call_result="empty_text",
                    )
                )
                continue

            logger.info(
                format_source_observable_log(
                    "provider_succeeded",
                    unified_msg_origin=unified_msg_origin,
                    source_label=source_label,
                    provider_id=provider_id,
                    attempt=str(attempt),
                    summary_length=str(len(completion_text)),
                )
            )
            return ForwardSummaryResult(
                success=True,
                provider_id=provider_id,
                prompt=prompt,
                text=completion_text,
                detail=completion_text,
            )

        return self._transient_failure(
            detail="转发总结失败：消息解析模型连续 3 次未返回有效摘要。",
            provider_id=provider_id,
            prompt=prompt,
            source_label=source_label,
            unified_msg_origin=unified_msg_origin,
        )

    @staticmethod
    def _build_prompt(transcript: str) -> str:
        return _FORWARD_SUMMARY_PROMPT.format(transcript=transcript.strip())

    def _configuration_failure(
        self,
        detail: str,
        *,
        provider_id: str,
        prompt: str,
        source_label: str,
        unified_msg_origin: str,
    ) -> ForwardSummaryResult:
        logger.warning(
            format_source_observable_log(
                "provider_configuration_error",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id or "<none>",
                call_result="configuration_error",
                detail=shorten_text(detail, 180),
            )
        )
        return ForwardSummaryResult(
            success=False,
            provider_id=provider_id,
            prompt=prompt,
            text=detail,
            detail=detail,
        )

    def _transient_failure(
        self,
        detail: str,
        *,
        provider_id: str,
        prompt: str,
        source_label: str,
        unified_msg_origin: str,
    ) -> ForwardSummaryResult:
        logger.warning(
            format_source_observable_log(
                "message_failed",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id,
                failure_stage="provider_call",
                detail=shorten_text(detail, 180),
            )
        )
        return ForwardSummaryResult(
            success=False,
            provider_id=provider_id,
            prompt=prompt,
            text=detail,
            detail=detail,
        )
