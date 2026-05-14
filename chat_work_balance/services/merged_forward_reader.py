from __future__ import annotations

# pyright: reportMissingImports=false

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Iterable, Sequence, cast

from astrbot.api.event import AstrMessageEvent
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
)

from .resource_analysis_service import ResourceAnalysisService


class ForwardTranscriptExtractionError(RuntimeError):
    """Raised when a merged forward message cannot produce any transcript entries."""

    def __init__(self, message: str, *, stats: "ForwardTranscriptStats | None" = None) -> None:
        super().__init__(message)
        self.stats = stats


@dataclass(frozen=True)
class ForwardTranscriptEntry:
    sender_name: str
    sender_id: str
    depth: int
    order: int
    text: str


@dataclass(frozen=True)
class ForwardLayerNote:
    depth: int
    text: str


@dataclass(frozen=True)
class ForwardTranscriptStats:
    total_nodes: int = 0
    kept_nodes: int = 0
    sampled_nodes: int = 0
    filtered_nodes: int = 0
    failed_forwards: int = 0
    truncated_layers: int = 0


@dataclass(frozen=True)
class ForwardTranscript:
    entries: tuple[ForwardTranscriptEntry, ...]
    notes: tuple[ForwardLayerNote, ...]
    stats: ForwardTranscriptStats


@dataclass(frozen=True)
class _ForwardNodeReference:
    identifier: str
    prefer_message_lookup: bool


class MergedForwardReader:
    """Extract transcript text from merged-forward content with per-layer sampling."""

    def __init__(
        self,
        max_depth: int = 3,
        max_nodes: int = 20,
        *,
        sample_threshold: int | None = None,
        sample_head_count: int | None = None,
        sample_tail_count: int | None = None,
    ) -> None:
        del max_nodes
        self._max_depth = max_depth
        self._sample_threshold = sample_threshold if sample_threshold is not None else 50
        self._sample_head_count = sample_head_count if sample_head_count is not None else 30
        self._sample_tail_count = sample_tail_count if sample_tail_count is not None else 20

    async def extract(
        self,
        component: Forward | Node | Nodes,
        *,
        event: AstrMessageEvent | object | None = None,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> ForwardTranscript:
        state = _ExtractionState(
            entries=[],
            notes=[],
            stats=_MutableForwardTranscriptStats(),
            order=0,
        )
        await self._append_component(
            component,
            depth=0,
            state=state,
            event=event,
            resource_analysis_service=resource_analysis_service,
            unified_msg_origin=unified_msg_origin,
            source_label=source_label,
        )
        if not state.entries:
            stats = state.stats.freeze()
            raise ForwardTranscriptExtractionError(
                "Merged forward transcript extraction produced no valid content.",
                stats=stats,
            )
        return ForwardTranscript(
            entries=tuple(state.entries),
            notes=tuple(state.notes),
            stats=state.stats.freeze(),
        )

    async def summarize(
        self,
        component: Forward | Node | Nodes,
        *,
        event: AstrMessageEvent | object | None = None,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> str:
        transcript = await self.extract(
            component,
            event=event,
            resource_analysis_service=resource_analysis_service,
            unified_msg_origin=unified_msg_origin,
            source_label=source_label,
        )
        lines = [
            self._format_entry(entry)
            for entry in transcript.entries
        ]
        lines.extend(note.text for note in transcript.notes)
        return "\n".join(line for line in lines if line).strip()

    async def _append_component(
        self,
        component: BaseMessageComponent,
        *,
        depth: int,
        state: "_ExtractionState",
        event: AstrMessageEvent | object | None,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> None:
        if isinstance(component, Nodes):
            await self._append_nodes(
                component.nodes,
                depth=depth,
                state=state,
                event=event,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
            )
            return

        if isinstance(component, Node):
            await self._append_node(
                component,
                depth=depth,
                state=state,
                event=event,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
            )
            return

        if isinstance(component, Forward):
            await self._append_forward_reference(
                component,
                depth=depth,
                state=state,
                event=event,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=source_label,
            )
            return

        state.stats.filtered_nodes += 1

    async def _append_nodes(
        self,
        nodes: Iterable[Node],
        *,
        depth: int,
        state: "_ExtractionState",
        event: AstrMessageEvent | object | None,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> None:
        if depth >= self._max_depth:
            state.stats.truncated_layers += 1
            return

        materialized = list(nodes)
        state.stats.total_nodes += len(materialized)
        selected_nodes, skipped_count = self._select_layer_nodes(materialized)
        state.stats.sampled_nodes += skipped_count
        if skipped_count > 0:
            state.notes.append(
                ForwardLayerNote(
                    depth=depth,
                    text=f"Skipped {skipped_count} nodes in this layer",
                )
            )
        for order_index, node in selected_nodes:
            if order_index < 0:
                continue

            await self._append_node(
                node,
                depth=depth,
                state=state,
                event=event,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=f"{source_label}:{order_index}",
            )

    async def _append_node(
        self,
        node: Node,
        *,
        depth: int,
        state: "_ExtractionState",
        event: AstrMessageEvent | object | None,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> None:
        if depth >= self._max_depth:
            state.stats.truncated_layers += 1
            return

        text_parts: list[str] = []
        nested_components: list[tuple[int, BaseMessageComponent]] = []
        for index, child in enumerate(node.content):
            nested_source_label = f"{source_label}#{index}"
            if isinstance(child, (Nodes, Node, Forward)):
                nested_components.append((index, child))
                continue

            text = await self._describe_leaf(
                child,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=nested_source_label,
            )
            if text:
                text_parts.append(text)

        kept_before_nested = state.stats.kept_nodes
        text = "".join(part for part in text_parts if part).strip()
        if text:
            state.entries.append(
                ForwardTranscriptEntry(
                    sender_name=(node.name or "").strip() or "unknown",
                    sender_id=(node.uin or "").strip(),
                    depth=depth,
                    order=state.order,
                    text=text,
                )
            )
            state.order += 1
            state.stats.kept_nodes += 1

        for index, child in nested_components:
            await self._append_component(
                child,
                depth=depth + 1,
                state=state,
                event=event,
                resource_analysis_service=resource_analysis_service,
                unified_msg_origin=unified_msg_origin,
                source_label=f"{source_label}#{index}",
            )

        if not text and state.stats.kept_nodes == kept_before_nested:
            state.stats.filtered_nodes += 1

    async def _append_forward_reference(
        self,
        component: Forward,
        *,
        depth: int,
        state: "_ExtractionState",
        event: AstrMessageEvent | object | None,
        resource_analysis_service: ResourceAnalysisService,
        unified_msg_origin: str,
        source_label: str,
    ) -> None:
        if depth >= self._max_depth:
            state.stats.truncated_layers += 1
            return

        forward_id = self._extract_forward_id(component)
        if not forward_id:
            state.stats.failed_forwards += 1
            state.stats.filtered_nodes += 1
            return

        resolved_forward = await self._resolve_forward_nodes(event, forward_id)
        if resolved_forward is None:
            state.stats.failed_forwards += 1
            state.stats.filtered_nodes += 1
            return
        forward_nodes, filtered_count = resolved_forward
        state.stats.filtered_nodes += filtered_count

        await self._append_nodes(
            forward_nodes,
            depth=depth,
            state=state,
            event=event,
            resource_analysis_service=resource_analysis_service,
            unified_msg_origin=unified_msg_origin,
            source_label=f"{source_label}:forward:{forward_id}",
        )

    async def _resolve_forward_nodes(
        self,
        event: AstrMessageEvent | object | None,
        forward_id: str,
    ) -> tuple[list[Node], int] | None:
        bot = getattr(event, "bot", None)
        if bot is None:
            return None

        response = await self._fetch_forward_response(bot, forward_id)
        if response is None:
            return None

        return await self._coerce_response_nodes(response, event=event)

    async def _fetch_forward_response(self, bot: object, forward_id: str) -> object | None:
        response = await self._fetch_from_bound_method(
            getattr(bot, "get_forward_msg", None),
            forward_id,
            ({}, {"id": forward_id}, {"message_id": forward_id}),
        )
        if response is not None:
            return response
        return await self._fetch_from_call_actions(
            bot,
            "get_forward_msg",
            (
                {"message_id": forward_id},
                {"id": forward_id},
                {"forward_id": forward_id},
            ),
        )

    @staticmethod
    def _iter_call_action_methods(bot: object) -> Iterable[Callable[..., object]]:
        call_action = getattr(bot, "call_action", None)
        if callable(call_action):
            yield call_action

        api = getattr(bot, "api", None)
        api_call_action = getattr(api, "call_action", None)
        if callable(api_call_action):
            yield api_call_action

    async def _resolve_message_reference_nodes(
        self,
        event: AstrMessageEvent | object | None,
        message_id: str,
    ) -> tuple[list[Node], int] | None:
        bot = getattr(event, "bot", None)
        if bot is None:
            return None

        response = await self._fetch_message_response(bot, message_id)
        if response is None:
            return None

        return await self._coerce_response_nodes(
            response,
            event=event,
            require_nodes=True,
        )

    async def _fetch_message_response(self, bot: object, message_id: str) -> object | None:
        response = await self._fetch_from_bound_method(
            getattr(bot, "get_msg", None),
            message_id,
            ({}, {"message_id": message_id}, {"id": message_id}),
        )
        if response is not None:
            return response
        return await self._fetch_from_call_actions(
            bot,
            "get_msg",
            ({"message_id": message_id}, {"id": message_id}),
        )

    async def _coerce_response_nodes(
        self,
        response: object,
        *,
        event: AstrMessageEvent | object | None,
        require_nodes: bool = False,
    ) -> tuple[list[Node], int] | None:
        raw_messages = self._extract_forward_messages(response)
        if raw_messages is None:
            return None

        nodes: list[Node] = []
        filtered_count = 0
        for item in raw_messages:
            coerced_nodes, node_filtered_count = await self._coerce_forward_nodes(
                item,
                event=event,
            )
            filtered_count += node_filtered_count
            nodes.extend(coerced_nodes)
        if require_nodes and not nodes:
            return None
        return nodes, filtered_count

    async def _fetch_from_bound_method(
        self,
        method: object,
        identifier: str,
        kwargs_options: Sequence[dict[str, object]],
    ) -> object | None:
        if not callable(method):
            return None

        for kwargs in kwargs_options:
            try:
                if kwargs:
                    response = await cast(Callable[..., Awaitable[object]], method)(
                        **kwargs
                    )
                else:
                    response = await cast(Callable[[str], Awaitable[object]], method)(
                        identifier
                    )
            except Exception:
                continue
            if self._extract_forward_messages(response) is not None:
                return response
        return None

    async def _fetch_from_call_actions(
        self,
        bot: object,
        action: str,
        kwargs_options: Sequence[dict[str, object]],
    ) -> object | None:
        for call_action in self._iter_call_action_methods(bot):
            for kwargs in kwargs_options:
                try:
                    response = await cast(Callable[..., Awaitable[object]], call_action)(
                        action,
                        **kwargs,
                    )
                except Exception:
                    continue
                if self._extract_forward_messages(response) is not None:
                    return response
        return None

    def _extract_forward_messages(self, response: object) -> Sequence[object] | None:
        direct_messages = self._normalize_message_sequence(response)
        if direct_messages is not None:
            return direct_messages

        if not isinstance(response, dict):
            return None

        data = response.get("data")
        data_sequence = self._normalize_message_sequence(data)
        if data_sequence is not None:
            return data_sequence
        if isinstance(data, dict):
            if self._looks_like_forward_node(data):
                return [data]
            for key in ("messages", "message"):
                data_messages = self._normalize_message_sequence(data.get(key))
                if data_messages is not None:
                    return data_messages

        if self._looks_like_forward_node(response):
            return [response]
        for key in ("messages", "message"):
            messages = self._normalize_message_sequence(response.get(key))
            if messages is not None:
                return messages

        return None

    @staticmethod
    def _normalize_message_sequence(value: object) -> Sequence[object] | None:
        if isinstance(value, (str, bytes, bytearray)):
            return None
        if isinstance(value, Sequence):
            return value
        return None

    @staticmethod
    def _looks_like_forward_node(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        if value.get("type") == "node":
            return True
        if "content" in value:
            return True
        if "message" in value:
            return any(
                key in value
                for key in ("sender", "user_id", "uin", "nickname", "name")
            )
        return False

    @staticmethod
    def _extract_forward_id(component: Forward) -> str:
        for attr in ("id", "forward_id", "message_id"):
            value = getattr(component, attr, None)
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                return normalized

        data = getattr(component, "data", None)
        if isinstance(data, dict):
            for key in ("id", "forward_id", "message_id"):
                value = data.get(key)
                if value is None:
                    continue
                normalized = str(value).strip()
                if normalized:
                    return normalized

        return ""

    async def _coerce_forward_nodes(
        self,
        item: object,
        *,
        event: AstrMessageEvent | object | None,
    ) -> tuple[list[Node], int]:
        if isinstance(item, Node):
            return [item], 0

        if not isinstance(item, dict):
            return [], 1

        segment_type = item.get("type")
        if isinstance(segment_type, str) and segment_type.strip() and segment_type != "node":
            return [], 1

        data: dict[object, object] | None = None
        if segment_type == "node":
            raw_data = item.get("data")
            if isinstance(raw_data, dict):
                data = raw_data
        elif "content" in item or "message" in item:
            data = item

        if not isinstance(data, dict):
            return [], 1

        normalized: list[BaseMessageComponent] = []
        filtered_count = 0
        node_reference = self._extract_forward_node_reference(data)
        content = data.get("content")
        if content is None:
            content = data.get("message")
        if node_reference and self._is_reference_only_node(data):
            reference_nodes = await self._append_node_reference(
                normalized,
                node_reference=node_reference,
                event=event,
            )
            if reference_nodes is not None:
                return reference_nodes
        elif isinstance(content, str):
            normalized.append(Plain(content))
        elif isinstance(content, list):
            for component in content:
                normalized_component, component_filtered_count = await self._coerce_forward_component(
                    component,
                    event=event,
                )
                filtered_count += component_filtered_count
                if normalized_component is not None:
                    normalized.append(normalized_component)
        elif node_reference:
            reference_nodes = await self._append_node_reference(
                normalized,
                node_reference=node_reference,
                event=event,
            )
            if reference_nodes is not None:
                return reference_nodes
        else:
            return [], 1

        if not normalized:
            return [], filtered_count + 1

        sender = data.get("sender")
        sender_data = sender if isinstance(sender, dict) else {}
        return (
            [
                Node(
                    name=self._normalize_sender_name(
                        data.get("nickname")
                        or data.get("name")
                        or sender_data.get("nickname")
                        or sender_data.get("card")
                        or sender_data.get("name")
                    ),
                    uin=self._normalize_sender_id(
                        data.get("user_id")
                        or data.get("uin")
                        or sender_data.get("user_id")
                        or sender_data.get("uin")
                    ),
                    content=normalized,
                ),
            ],
            filtered_count,
        )

    async def _append_node_reference(
        self,
        normalized: list[BaseMessageComponent],
        *,
        node_reference: _ForwardNodeReference,
        event: AstrMessageEvent | object | None,
    ) -> tuple[list[Node], int] | None:
        reference_component, filtered_count = await self._coerce_node_reference(
            node_reference=node_reference,
            event=event,
        )
        if isinstance(reference_component, Nodes):
            return reference_component.nodes, filtered_count
        normalized.append(reference_component)
        return None

    async def _coerce_forward_component(
        self,
        item: object,
        *,
        event: AstrMessageEvent | object | None,
    ) -> tuple[BaseMessageComponent | None, int]:
        if isinstance(item, BaseMessageComponent):
            return item, 0

        if not isinstance(item, dict):
            return None, 1

        segment_type = item.get("type")
        data = item.get("data")
        if not isinstance(segment_type, str) or not isinstance(data, dict):
            return None, 1

        if segment_type == "text":
            text = data.get("text", "")
            return Plain(str(text)), 0
        if segment_type == "image":
            file = data.get("file")
            url = data.get("url")
            image_ref = str(url or file or "")
            return Image(file=image_ref, url=str(url or "")), 0
        if segment_type in {"file", "record", "video"}:
            return None, 1
        if segment_type == "at":
            qq = data.get("qq")
            return At(qq=str(qq or "")), 0
        if segment_type == "face":
            face_id = data.get("id")
            return Face(id=str(face_id or "")), 0
        if segment_type == "mface":
            summary = str(data.get("summary") or data.get("emoji_id") or "").strip()
            return Plain(f"Sticker: {summary}" if summary else "Sticker"), 0
        if segment_type == "reply":
            return Reply(id=str(data.get("id", "")).strip()), 0
        if segment_type == "forward":
            forward_id = data.get("id")
            normalized_id = str(forward_id or "").strip()
            return (Forward(id=normalized_id), 0) if normalized_id else (None, 1)
        if segment_type == "node":
            node_reference = self._extract_forward_node_reference(data)
            if node_reference and self._is_reference_only_node(data):
                reference_component, reference_filtered_count = await self._coerce_node_reference(
                    node_reference=node_reference,
                    event=event,
                )
                return reference_component, reference_filtered_count
            nodes, filtered_count = await self._coerce_forward_nodes(
                item,
                event=event,
            )
            if len(nodes) == 1:
                return nodes[0], filtered_count
            if nodes:
                return Nodes(nodes=nodes), filtered_count
            return (
                (Forward(id=node_reference.identifier), filtered_count)
                if node_reference
                else (None, filtered_count + 1)
            )
        return None, 1

    async def _coerce_node_reference(
        self,
        *,
        node_reference: _ForwardNodeReference,
        event: AstrMessageEvent | object | None,
    ) -> tuple[BaseMessageComponent, int]:
        if not node_reference.prefer_message_lookup:
            return Forward(id=node_reference.identifier), 0

        resolved_nodes = await self._resolve_message_reference_nodes(
            event,
            node_reference.identifier,
        )
        if resolved_nodes is None:
            return Forward(id=node_reference.identifier), 0
        nodes, filtered_count = resolved_nodes
        if nodes:
            filtered_count -= len(nodes)
        return Nodes(nodes=nodes), max(filtered_count, 0)

    @staticmethod
    def _is_reference_only_node(data: dict[object, object]) -> bool:
        has_sender_context = any(
            key in data
            for key in ("sender", "user_id", "uin", "nickname", "name")
        )
        if has_sender_context:
            return False
        content = data.get("content")
        message = data.get("message")
        return isinstance(content, str) or isinstance(message, str) or (
            content is None and message is None
        )

    @staticmethod
    def _extract_forward_node_reference(
        data: dict[object, object],
    ) -> _ForwardNodeReference | None:
        for key in ("id", "message_id"):
            value = data.get(key)
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                return _ForwardNodeReference(
                    identifier=normalized,
                    prefer_message_lookup=True,
                )

        for key in ("forward_id", "resid"):
            value = data.get(key)
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                return _ForwardNodeReference(
                    identifier=normalized,
                    prefer_message_lookup=False,
                )

        for key in ("content", "message"):
            value = data.get(key)
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if normalized:
                return _ForwardNodeReference(
                    identifier=normalized,
                    prefer_message_lookup=False,
                )
        return None

    def _select_layer_nodes(
        self,
        nodes: Sequence[Node],
    ) -> tuple[list[tuple[int, Node]], int]:
        if len(nodes) <= self._sample_threshold:
            return list(enumerate(nodes)), 0

        selected_indexes = list(range(min(self._sample_head_count, len(nodes))))
        tail_start = max(len(nodes) - self._sample_tail_count, 0)
        selected_indexes.extend(range(tail_start, len(nodes)))

        deduped_indexes: list[int] = []
        seen: set[int] = set()
        for index in selected_indexes:
            if index in seen:
                continue
            seen.add(index)
            deduped_indexes.append(index)

        skipped_count = len(nodes) - len(deduped_indexes)
        return [(index, nodes[index]) for index in deduped_indexes], skipped_count

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
            return analysis.text.strip()
        if isinstance(component, (File, Record)):
            return ""
        if isinstance(component, At):
            return f"At: {component.qq}"
        if isinstance(component, Face):
            return "Face emoji"
        if isinstance(component, Reply):
            return f"Reply to {component.id}"
        return ""

    @staticmethod
    def _format_entry(entry: ForwardTranscriptEntry) -> str:
        sender = entry.sender_name
        if entry.sender_id:
            sender = f"{sender}({entry.sender_id})"
        return f"{'  ' * entry.depth}{sender}: {entry.text}"

    @staticmethod
    def _normalize_sender_name(value: object) -> str:
        if isinstance(value, str):
            return value.strip() or "unknown"
        return str(value).strip() or "unknown"

    @staticmethod
    def _normalize_sender_id(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


@dataclass
class _MutableForwardTranscriptStats:
    total_nodes: int = 0
    kept_nodes: int = 0
    sampled_nodes: int = 0
    filtered_nodes: int = 0
    failed_forwards: int = 0
    truncated_layers: int = 0

    def freeze(self) -> ForwardTranscriptStats:
        return ForwardTranscriptStats(
            total_nodes=self.total_nodes,
            kept_nodes=self.kept_nodes,
            sampled_nodes=self.sampled_nodes,
            filtered_nodes=self.filtered_nodes,
            failed_forwards=self.failed_forwards,
            truncated_layers=self.truncated_layers,
        )


@dataclass
class _ExtractionState:
    entries: list[ForwardTranscriptEntry]
    notes: list[ForwardLayerNote]
    stats: _MutableForwardTranscriptStats
    order: int
