from __future__ import annotations

# pyright: reportMissingImports=false

from dataclasses import dataclass

from astrbot.api.star import Context
from astrbot.core.provider.provider import Provider


@dataclass(frozen=True)
class ProviderLookup:
    provider: Provider | None
    failure_detail: str = ""


def lookup_chat_provider(
    context: Context,
    provider_id: str,
    *,
    not_configured_detail: str,
    not_found_detail: str,
    invalid_type_detail: str,
) -> ProviderLookup:
    if not provider_id:
        return ProviderLookup(provider=None, failure_detail=not_configured_detail)

    provider = context.get_provider_by_id(provider_id)
    if provider is None:
        return ProviderLookup(provider=None, failure_detail=not_found_detail)
    if not isinstance(provider, Provider):
        return ProviderLookup(provider=None, failure_detail=invalid_type_detail)
    return ProviderLookup(provider=provider)


def extract_completion_text(response: object) -> str:
    return (getattr(response, "completion_text", "") or "").strip()
