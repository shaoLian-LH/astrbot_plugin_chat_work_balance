from __future__ import annotations

from ..models import ReplayPlan, ResolvedMessage


class QQChannelMessageResolver:
    """Slice A keeps a stable resolver contract; parsing lands in Slice B."""

    def __init__(self, merged_forward_reader, resource_analysis_service) -> None:
        self._merged_forward_reader = merged_forward_reader
        self._resource_analysis_service = resource_analysis_service

    async def resolve(self, event) -> ResolvedMessage:
        return ResolvedMessage(
            log_summary=(
                "QQChannelMessageResolver skeleton consumed message "
                f"{event.unified_msg_origin}."
            ),
            replay_plan=ReplayPlan(),
        )


__all__ = ["QQChannelMessageResolver", "ReplayPlan", "ResolvedMessage"]
