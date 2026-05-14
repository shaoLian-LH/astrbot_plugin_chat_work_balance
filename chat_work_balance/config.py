from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass
from typing import Any

from astrbot.api import AstrBotConfig


@dataclass(frozen=True)
class ChatWorkBalanceConfig:
    image_analysis_provider_id: str = ""
    message_resolve_provider_id: str = ""
    forward_max_depth: int = 3
    forward_sample_threshold: int = 50
    forward_sample_head_count: int = 30
    forward_sample_tail_count: int = 20

    @classmethod
    def from_astrbot_config(
        cls,
        config: AstrBotConfig | dict[str, object] | None,
    ) -> "ChatWorkBalanceConfig":
        if config is None:
            return cls()

        return cls(
            image_analysis_provider_id=cls._normalize_str(
                config.get("image_analysis_provider_id", "")
            ),
            message_resolve_provider_id=cls._normalize_str(
                config.get("message_resolve_provider_id", "")
            ),
            forward_max_depth=cls._normalize_non_negative_int(
                config.get("forward_max_depth", 3),
                default=3,
            ),
            forward_sample_threshold=cls._normalize_non_negative_int(
                config.get("forward_sample_threshold", 50),
                default=50,
            ),
            forward_sample_head_count=cls._normalize_non_negative_int(
                config.get("forward_sample_head_count", 30),
                default=30,
            ),
            forward_sample_tail_count=cls._normalize_non_negative_int(
                config.get("forward_sample_tail_count", 20),
                default=20,
            ),
        )

    @staticmethod
    def get_provider_settings(
        config: AstrBotConfig | dict[str, Any] | None,
    ) -> dict[str, Any]:
        if config is None:
            return {}

        provider_settings = config.get("provider_settings", {})
        if isinstance(provider_settings, dict):
            return provider_settings
        return {}

    def resolve_provider_id(
        self,
        global_config: AstrBotConfig | dict[str, Any] | None,
    ) -> str:
        if self.image_analysis_provider_id:
            return self.image_analysis_provider_id

        provider_settings = self.get_provider_settings(global_config)
        provider_id = provider_settings.get("default_image_caption_provider_id", "")
        if isinstance(provider_id, str):
            return provider_id.strip()
        return str(provider_id).strip()

    def resolve_message_provider_id(
        self,
        global_config: AstrBotConfig | dict[str, Any] | None,
    ) -> str:
        if self.message_resolve_provider_id:
            return self.message_resolve_provider_id

        provider_settings = self.get_provider_settings(global_config)
        provider_id = provider_settings.get("default_message_resolve_provider_id", "")
        return self._normalize_str(provider_id)

    def resolve_prompt(
        self,
        global_config: AstrBotConfig | dict[str, Any] | None,
    ) -> str:
        provider_settings = self.get_provider_settings(global_config)
        prompt = provider_settings.get("image_caption_prompt", "")
        return self._normalize_str(prompt)

    @staticmethod
    def _normalize_str(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _normalize_non_negative_int(value: object, *, default: int) -> int:
        if isinstance(value, bool):
            return int(value)
        if not isinstance(value, (int, float, str)):
            return default
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return default
        return normalized if normalized >= 0 else default
