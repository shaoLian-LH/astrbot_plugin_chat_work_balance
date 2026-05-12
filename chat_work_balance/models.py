from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolvedSegment:
    kind: str
    payload: Any | None = None


@dataclass(frozen=True)
class ReplayChunk:
    chain: list[Any]
    source_indexes: tuple[int, ...] = ()


@dataclass(frozen=True)
class ReplayPlan:
    chunks: list[ReplayChunk] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedMessage:
    log_summary: str
    segments: list[ResolvedSegment] = field(default_factory=list)
    replay_plan: ReplayPlan = field(default_factory=ReplayPlan)
