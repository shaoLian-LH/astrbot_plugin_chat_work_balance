from __future__ import annotations

# pyright: reportMissingImports=false

from typing import Iterable

from astrbot.core.message.components import (
    At,
    BaseMessageComponent,
    Face,
    File,
    Forward,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Video,
)

from .resource_analysis_service import ResourceAnalysisService


class MergedForwardReader:
    """Read merged-forward content into a bounded text summary."""

    def __init__(self, max_depth: int = 3, max_nodes: int = 20) -> None:
        self._max_depth = max_depth
        self._max_nodes = max_nodes

    async def summarize(
        self,
        component: Forward | Node | Nodes,
        *,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> str:
        lines: list[str] = []
        state = {"visited": 0, "truncated": False}
        await self._append_component_summary(
            component,
            lines=lines,
            depth=0,
            state=state,
            resource_analysis_service=resource_analysis_service,
            unified_msg_origin=unified_msg_origin,
            source_label=source_label,
        )
        if state["truncated"]:
            lines.append("Forward summary truncated: max depth or node limit reached.")
        return "\n".join(line for line in lines if line).strip() or "Forward summary unavailable."

    async def _append_component_summary(
        self,
        component: BaseMessageComponent,
        *,
        lines: list[str],
        depth: int,
        state: dict[str, bool | int],
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> None:
        if depth >= self._max_depth:
            state["truncated"] = True
            lines.append(f"{self._indent(depth)}[Max depth reached]")
            return

        if isinstance(component, Nodes):
            await self._append_nodes(
                component.nodes,
                lines=lines,
                depth=depth,
                state=state,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
            )
            return

        if isinstance(component, Node):
            state["visited"] = int(state["visited"]) + 1
            if int(state["visited"]) > self._max_nodes:
                state["truncated"] = True
                return
            author = component.name or component.uin or "unknown"
            lines.append(f"{self._indent(depth)}Node from {author}:")
            for child in component.content:
                await self._append_component_summary(
                    child,
                    lines=lines,
                    depth=depth + 1,
                    state=state,
                    resource_analysis_service=resource_analysis_service,
                    unified_msg_origin=unified_msg_origin,
                    source_label=source_label,
                )
            return

        if isinstance(component, Forward):
            lines.append(f"{self._indent(depth)}Forward reference: {component.id}")
            return

        summary_line = await self._describe_leaf(
            component,
            resource_analysis_service=resource_analysis_service,
            unified_msg_origin=unified_msg_origin,
            source_label=source_label,
        )
        lines.append(f"{self._indent(depth)}{summary_line}")

    async def _append_nodes(
        self,
        nodes: Iterable[Node],
        *,
        lines: list[str],
        depth: int,
        state: dict[str, bool | int],
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> None:
        for node in nodes:
            await self._append_component_summary(
                node,
                lines=lines,
                depth=depth,
                state=state,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
            )
            if bool(state["truncated"]):
                return

    async def _describe_leaf(
        self,
        component: BaseMessageComponent,
        *,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> str:
        if isinstance(component, Plain):
            return component.text
        if isinstance(component, Image):
            analysis = await resource_analysis_service.analyze_image(
                component,
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
            )
            return analysis.text
        if isinstance(component, File):
            return f"File: {component.name or 'unnamed'}"
        if isinstance(component, Record):
            return "Voice message"
        if isinstance(component, Video):
            return "Video message"
        if isinstance(component, At):
            return f"At: {component.qq}"
        if isinstance(component, Face):
            return "Face emoji"
        if isinstance(component, Reply):
            return f"Reply to {component.id}"
        if isinstance(component, Nodes):
            return "Nested forward nodes"
        return f"Unsupported forward component: {type(component).__name__}"

    @staticmethod
    def _indent(depth: int) -> str:
        return "  " * depth
