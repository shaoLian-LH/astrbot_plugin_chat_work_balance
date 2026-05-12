from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ResolvedSegment:
    kind: Literal[
        "plain",
        "image",
        "image_analysis",
        "file",
        "record",
        "video",
        "reply",
        "face",
        "at",
        "forward_summary",
        "unknown",
    ]
    summary: str
    payload: Any | None = None
    source_index: int = -1
    replayable: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayChunk:
    chain: list[Any]
    source_indexes: tuple[int, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class ReplayPlan:
    chunks: list[ReplayChunk] = field(default_factory=list)
    dropped_segments: list[ResolvedSegment] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedMessage:
    log_summary: str
    segments: list[ResolvedSegment] = field(default_factory=list)
    replay_plan: ReplayPlan = field(default_factory=ReplayPlan)
