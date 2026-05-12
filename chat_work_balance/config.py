from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass
from typing import Any

from astrbot.api import AstrBotConfig


@dataclass(frozen=True)
class ChatWorkBalanceConfig:
    image_analysis_provider_id: str = ""

    @classmethod
    def from_astrbot_config(
        cls,
        config: AstrBotConfig | dict[str, object] | None,
    ) -> "ChatWorkBalanceConfig":
        if config is None:
            return cls()

        provider_id = config.get("image_analysis_provider_id", "")
        if not isinstance(provider_id, str):
            provider_id = str(provider_id)
        return cls(image_analysis_provider_id=provider_id.strip())

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

    def resolve_prompt(
        self,
        global_config: AstrBotConfig | dict[str, Any] | None,
    ) -> str:
        provider_settings = self.get_provider_settings(global_config)
        prompt = provider_settings.get("image_caption_prompt", "")
        if isinstance(prompt, str):
            return prompt.strip()
        return str(prompt).strip()
