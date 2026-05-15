from __future__ import annotations

_PLUGIN_NAME = "chat_work_balance"


def format_observable_log(
    stage: str,
    *,
    unified_msg_origin: str,
    message_id: str,
    platform: str | None = None,
    **fields: str,
) -> str:
    resolved_platform = (
        platform if platform is not None else resolve_platform(unified_msg_origin)
    )
    parts = [
        f"plugin={_PLUGIN_NAME}",
        f"stage={stage}",
        f"platform={resolved_platform}",
        f"unified_msg_origin={unified_msg_origin}",
        f"message_id={message_id}",
    ]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    return " ".join(parts)


def format_source_observable_log(
    stage: str,
    *,
    unified_msg_origin: str,
    source_label: str,
    provider_id: str,
    **fields: str,
) -> str:
    return format_observable_log(
        stage,
        unified_msg_origin=unified_msg_origin,
        message_id=extract_message_id(source_label),
        source_label=source_label,
        provider_id=provider_id,
        **fields,
    )


def resolve_platform(unified_msg_origin: str) -> str:
    if not unified_msg_origin:
        return "<unknown>"
    return unified_msg_origin.split(":", 1)[0] or "<unknown>"


def extract_message_id(source_label: str) -> str:
    if source_label.startswith("message:"):
        message_part = source_label.split(":", 1)[1]
        return message_part.split("#", 1)[0] or "<unknown>"
    if source_label.startswith("forward:"):
        message_part = source_label.split(":", 1)[1]
        return message_part.split("#", 1)[0] or "<unknown>"
    return "<unknown>"


def shorten_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."
