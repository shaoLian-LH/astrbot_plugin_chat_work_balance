from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

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
        return cls(image_analysis_provider_id=provider_id)
