from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.core.message.components import Image
from astrbot.core.provider.provider import Provider

from ..config import ChatWorkBalanceConfig


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
            )

        provider = self._context.get_provider_by_id(provider_id)
        if provider is None:
            return self._failure(
                "provider_selection",
                f"Image analysis skipped: provider '{provider_id}' was not found.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
            )
        if not isinstance(provider, Provider):
            return self._failure(
                "provider_selection",
                f"Image analysis skipped: provider '{provider_id}' is not a chat provider.",
                provider_id=provider_id,
                prompt=prompt,
                source_label=source_label,
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
            )

        summary_text = f"Image analysis: {completion_text}"
        logger.info(
            "Image analysis succeeded: source=%s provider=%s detail=%s",
            source_label,
            provider_id,
            self._shorten(completion_text),
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
        error_type: str = "",
    ) -> ResourceAnalysisResult:
        logger.warning(
            "Image analysis degraded: source=%s stage=%s provider=%s error_type=%s detail=%s",
            source_label,
            stage,
            provider_id or "<none>",
            error_type or "<none>",
            self._shorten(detail),
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
