from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.message.components import Image
from astrbot.core.provider.provider import Provider

from ..config import ChatWorkBalanceConfig

_PLUGIN_NAME = "chat_work_balance"


@dataclass(frozen=True)
class ResourceAnalysisResult:
    success: bool
    provider_id: str
    prompt: str
    text: str
    detail: str


class ResourceAnalysisService:
    """Normalize image input and route analysis to the configured provider."""

    def __init__(self, context: Context, plugin_config: ChatWorkBalanceConfig) -> None:
        self._context = context
        self._plugin_config = plugin_config

    async def analyze_image(
        self,
        image: Image,
        *,
        unified_msg_origin: str,
        source_label: str,
    ) -> ResourceAnalysisResult:
        global_config = self._context.get_config(unified_msg_origin)
        provider_id = self._plugin_config.resolve_provider_id(global_config)
        prompt = self._plugin_config.resolve_prompt(global_config)
        if not prompt:
            prompt = "Describe this image briefly for message replay."

        if not provider_id:
            return self._failure(
                "provider_selection",
                "Image analysis skipped: no provider configured.",
                provider_id="",
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )

        provider = self._context.get_provider_by_id(provider_id)
        if provider is None:
            return self._failure(
                "provider_selection",
                f"Image analysis skipped: provider '{provider_id}' was not found.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )
        if not isinstance(provider, Provider):
            return self._failure(
                "provider_selection",
                f"Image analysis skipped: provider '{provider_id}' is not a chat provider.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )

        try:
            image_ref = await self._normalize_image(image)
        except Exception as exc:
            return self._failure(
                "image_normalization",
                "Image analysis failed during image normalization.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
                error_type=type(exc).__name__,
            )

        try:
            response = await provider.text_chat(prompt=prompt, image_urls=[image_ref])
        except Exception as exc:
            return self._failure(
                "provider_call",
                "Image analysis failed during provider call.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
                error_type=type(exc).__name__,
            )

        completion_text = (getattr(response, "completion_text", "") or "").strip()
        if not completion_text:
            return self._failure(
                "provider_call",
                "Image analysis failed: provider returned empty text.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )

        summary_text = f"Image analysis: {completion_text}"
        logger.info(
            self._format_observable_log(
                "provider_succeeded",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id,
                detail=self._shorten(completion_text),
            )
        )
        return ResourceAnalysisResult(
            success=True,
            provider_id=provider_id,
            prompt=prompt,
            text=summary_text,
            detail=completion_text,
        )

    async def _normalize_image(self, image: Image) -> str:
        try:
            image_path = await image.convert_to_file_path()
            return f"file://{image_path}"
        except Exception:
            image_base64 = await image.convert_to_base64()
            return f"base64://{image_base64}"

    def _failure(
        self,
        stage: str,
        detail: str,
        *,
        provider_id: str,
        prompt: str,
        source_label: str,
        unified_msg_origin: str,
        error_type: str = "",
    ) -> ResourceAnalysisResult:
        logger.warning(
            self._format_observable_log(
                "message_failed",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id or "<none>",
                failure_stage=stage,
                error_type=error_type or "<none>",
                detail=self._shorten(detail),
            )
        )
        return ResourceAnalysisResult(
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
            f"platform={ResourceAnalysisService._resolve_platform(unified_msg_origin)}",
            f"unified_msg_origin={unified_msg_origin}",
            f"message_id={ResourceAnalysisService._extract_message_id(source_label)}",
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
