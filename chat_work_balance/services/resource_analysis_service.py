from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.message.components import Image

from ..config import ChatWorkBalanceConfig
from ..observability import format_source_observable_log, shorten_text
from .provider_utils import extract_completion_text, lookup_chat_provider


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

        provider_lookup = lookup_chat_provider(
            self._context,
            provider_id,
            not_configured_detail="Image analysis skipped: no provider configured.",
            not_found_detail=f"Image analysis skipped: provider '{provider_id}' was not found.",
            invalid_type_detail=f"Image analysis skipped: provider '{provider_id}' is not a chat provider.",
        )
        if provider_lookup.provider is None:
            return self._failure(
                "provider_selection",
                provider_lookup.failure_detail,
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
                unified_msg_origin=unified_msg_origin,
            )
        provider = provider_lookup.provider

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

        completion_text = extract_completion_text(response)
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
            format_source_observable_log(
                "provider_succeeded",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id,
                detail=shorten_text(completion_text, 180),
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
            format_source_observable_log(
                "message_failed",
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
                provider_id=provider_id or "<none>",
                failure_stage=stage,
                error_type=error_type or "<none>",
                detail=shorten_text(detail, 180),
            )
        )
        return ResourceAnalysisResult(
            success=False,
            provider_id=provider_id,
            prompt=prompt,
            text=detail,
            detail=detail,
        )
