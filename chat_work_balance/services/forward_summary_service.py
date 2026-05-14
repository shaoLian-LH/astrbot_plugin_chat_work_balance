from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.provider.provider import Provider

from ..config import ChatWorkBalanceConfig

_PLUGIN_NAME = "chat_work_balance"
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

        if not provider_id:
            return self._configuration_failure(
                detail="转发总结失败：未配置消息解析模型。",
                provider_id="",
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )

        provider = self._context.get_provider_by_id(provider_id)
        if provider is None:
            return self._configuration_failure(
                detail=f"转发总结失败：找不到消息解析模型 {provider_id}。",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )
        if not isinstance(provider, Provider):
            return self._configuration_failure(
                detail=f"转发总结失败：消息解析模型 {provider_id} 不是文本对话 provider。",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )

        for attempt in range(1, _MAX_PROVIDER_ATTEMPTS + 1):
            try:
                response = await provider.text_chat(prompt=prompt, image_urls=[])
            except Exception as exc:
                logger.warning(
                    self._format_observable_log(
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

            completion_text = (getattr(response, "completion_text", "") or "").strip()
            if not completion_text:
                logger.warning(
                    self._format_observable_log(
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
                self._format_observable_log(
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
            self._format_observable_log(
                "provider_configuration_error",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id or "<none>",
                call_result="configuration_error",
                detail=self._shorten(detail),
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
            self._format_observable_log(
                "message_failed",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id,
                failure_stage="provider_call",
                detail=self._shorten(detail),
            )
        )
        return ForwardSummaryResult(
            success=False,
            provider_id=provider_id,
            prompt=prompt,
            text=detail,
            detail=detail,
        )

    @staticmethod
    def _shorten(text: str, limit: int = 180) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3]}..."

    @staticmethod
    def _format_observable_log(
        stage: str,
        *,
        unified_msg_origin: str,
        source_label: str,
        provider_id: str,
        **fields: str,
    ) -> str:
        parts = [
            f"plugin={_PLUGIN_NAME}",
            f"stage={stage}",
            f"platform={ForwardSummaryService._resolve_platform(unified_msg_origin)}",
            f"unified_msg_origin={unified_msg_origin}",
            f"message_id={ForwardSummaryService._extract_message_id(source_label)}",
            f"source_label={source_label}",
            f"provider_id={provider_id}",
        ]
        for key, value in fields.items():
            parts.append(f"{key}={value}")
        return " ".join(parts)

    @staticmethod
    def _resolve_platform(unified_msg_origin: str) -> str:
        if not unified_msg_origin:
            return "<unknown>"
        return unified_msg_origin.split(":", 1)[0] or "<unknown>"

    @staticmethod
    def _extract_message_id(source_label: str) -> str:
        if source_label.startswith("message:"):
            message_part = source_label.split(":", 1)[1]
            return message_part.split("#", 1)[0] or "<unknown>"
        if source_label.startswith("forward:"):
            message_part = source_label.split(":", 1)[1]
            return message_part.split("#", 1)[0] or "<unknown>"
        return "<unknown>"
