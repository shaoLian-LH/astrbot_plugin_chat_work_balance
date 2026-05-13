from __future__ import annotations

# pyright: reportMissingImports=false

from typing import Iterable, Literal

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
    Video,
)

from ..models import ReplayChunk, ReplayPlan, ResolvedMessage, ResolvedSegment
from ..services.merged_forward_reader import MergedForwardReader
from ..services.resource_analysis_service import ResourceAnalysisService


class QQChannelMessageResolver:
    """Resolve full QQ Official message chains into replay-safe chunks."""

    def __init__(
        self,
        merged_forward_reader: MergedForwardReader,
        resource_analysis_service: ResourceAnalysisService,
    ) -> None:
        self._merged_forward_reader = merged_forward_reader
        self._resource_analysis_service = resource_analysis_service

    async def resolve(self, event: AstrMessageEvent) -> ResolvedMessage:
        message_obj = getattr(event, "message_obj", None)
        message_chain = getattr(message_obj, "message", None) or []
        segments: list[ResolvedSegment] = []
        chunks: list[ReplayChunk] = []
        dropped_segments: list[ResolvedSegment] = []

        text_buffer: list[Plain] = []
        text_indexes: list[int] = []

        async def flush_text_buffer() -> None:
            nonlocal text_buffer, text_indexes
            if not text_buffer:
                return
            chunks.append(
                ReplayChunk(
                    chain=list(text_buffer),
                    intent="text",
                    source_indexes=tuple(text_indexes),
                    summary=self._join_plain_text(text_buffer),
                )
            )
            text_buffer = []
            text_indexes = []

        def append_text_chunk(text: str, *, source_index: int) -> None:
            if not text:
                return
            text_buffer.append(Plain(text))
            text_indexes.append(source_index)

        def append_media_chunk(
            component: BaseMessageComponent,
            *,
            intent: Literal["image", "file", "record", "video"],
            source_index: int,
            summary: str,
        ) -> None:
            chunks.append(
                ReplayChunk(
                    chain=[component],
                    intent=intent,
                    source_indexes=(source_index,),
                    summary=summary,
                )
            )

        for index, component in enumerate(message_chain):
            if isinstance(component, Plain):
                text = component.text or ""
                segments.append(
                    ResolvedSegment(
                        kind="plain",
                        summary=text,
                        payload=component,
                        source_index=index,
                        replayable=True,
                    )
                )
                append_text_chunk(text, source_index=index)
                continue

            if isinstance(component, Image):
                await flush_text_buffer()
                image_summary = self._describe_image(component)
                segments.append(
                    ResolvedSegment(
                        kind="image",
                        summary=image_summary,
                        payload=component,
                        source_index=index,
                        replayable=True,
                    )
                )
                append_media_chunk(
                    component,
                    intent="image",
                    source_index=index,
                    summary=image_summary,
                )
                analysis = await self._resource_analysis_service.analyze_image(
                    component,
                    unified_msg_origin=event.unified_msg_origin,
                    source_label=f"message:{getattr(message_obj, 'message_id', 'unknown')}#{index}",
                )
                analysis_segment = ResolvedSegment(
                    kind="image_analysis",
                    summary=analysis.text,
                    payload=analysis.detail,
                    source_index=index,
                    replayable=True,
                    metadata={
                        "provider_id": analysis.provider_id,
                        "success": str(analysis.success).lower(),
                    },
                )
                segments.append(analysis_segment)
                append_text_chunk(analysis.text, source_index=index)
                continue

            if isinstance(component, File):
                await flush_text_buffer()
                replay_file, summary, metadata = await self._prepare_file_component(component)
                segments.append(
                    ResolvedSegment(
                        kind="file",
                        summary=summary,
                        payload=replay_file,
                        source_index=index,
                        replayable=True,
                        metadata=metadata,
                    )
                )
                append_media_chunk(
                    replay_file,
                    intent="file",
                    source_index=index,
                    summary=summary,
                )
                continue

            if isinstance(component, Record):
                await flush_text_buffer()
                summary = "Voice message"
                segments.append(
                    ResolvedSegment(
                        kind="record",
                        summary=summary,
                        payload=component,
                        source_index=index,
                        replayable=True,
                    )
                )
                append_media_chunk(
                    component,
                    intent="record",
                    source_index=index,
                    summary=summary,
                )
                continue

            if isinstance(component, Video):
                await flush_text_buffer()
                summary = "Video message"
                segments.append(
                    ResolvedSegment(
                        kind="video",
                        summary=summary,
                        payload=component,
                        source_index=index,
                        replayable=True,
                    )
                )
                append_media_chunk(
                    component,
                    intent="video",
                    source_index=index,
                    summary=summary,
                )
                continue

            if isinstance(component, At):
                segment = ResolvedSegment(
                    kind="at",
                    summary=f"At mention skipped: {component.qq}",
                    payload=component,
                    source_index=index,
                    replayable=False,
                )
                segments.append(segment)
                dropped_segments.append(segment)
                continue

            if isinstance(component, Face):
                segment = ResolvedSegment(
                    kind="face",
                    summary="Face emoji skipped in replay.",
                    payload=component,
                    source_index=index,
                    replayable=False,
                )
                segments.append(segment)
                dropped_segments.append(segment)
                continue

            if isinstance(component, Reply):
                segment = ResolvedSegment(
                    kind="reply",
                    summary=f"Reply reference skipped: {component.id}",
                    payload=component,
                    source_index=index,
                    replayable=False,
                )
                segments.append(segment)
                dropped_segments.append(segment)
                continue

            if isinstance(component, (Forward, Node, Nodes)):
                forward_summary = await self._merged_forward_reader.summarize(
                    component,
                    resource_analysis_service=self._resource_analysis_service,
                    unified_msg_origin=event.unified_msg_origin,
                    source_label=f"forward:{getattr(message_obj, 'message_id', 'unknown')}#{index}",
                )
                segments.append(
                    ResolvedSegment(
                        kind="forward_summary",
                        summary=forward_summary,
                        payload=component,
                        source_index=index,
                        replayable=True,
                    )
                )
                append_text_chunk(forward_summary, source_index=index)
                continue

            placeholder = f"Unsupported component preserved as text: {type(component).__name__}"
            segments.append(
                ResolvedSegment(
                    kind="unknown",
                    summary=placeholder,
                    payload=component,
                    source_index=index,
                    replayable=True,
                )
            )
            append_text_chunk(placeholder, source_index=index)

        await flush_text_buffer()

        replay_plan = ReplayPlan(chunks=chunks, dropped_segments=dropped_segments)
        return ResolvedMessage(
            log_summary=self._build_log_summary(event, message_chain, segments, replay_plan),
            segments=segments,
            replay_plan=replay_plan,
        )

    async def _prepare_file_component(
        self,
        component: File,
    ) -> tuple[File, str, dict[str, str]]:
        name = component.name or "unnamed"
        metadata: dict[str, str] = {"name": name}
        try:
            file_ref = await component.get_file(allow_return_url=True)
        except Exception as exc:
            metadata["source"] = "original"
            metadata["failure"] = type(exc).__name__
            replay_file = component
            summary = "File: {name} (original, lookup failed)".format(name=name)
            return replay_file, summary, metadata

        if file_ref.startswith("http://") or file_ref.startswith("https://"):
            metadata["source"] = "url"
            replay_file = File(name=name, url=file_ref)
        elif file_ref:
            metadata["source"] = "path"
            replay_file = File(name=name, file=file_ref)
        else:
            metadata["source"] = "original"
            replay_file = component
        summary = f"File: {name} ({metadata['source']})"
        return replay_file, summary, metadata

    def _build_log_summary(
        self,
        event: AstrMessageEvent,
        message_chain: Iterable[BaseMessageComponent],
        segments: list[ResolvedSegment],
        replay_plan: ReplayPlan,
    ) -> str:
        message_obj = getattr(event, "message_obj", None)
        message_id = str(getattr(message_obj, "message_id", ""))
        component_names = [type(component).__name__ for component in message_chain]
        image_results = [
            segment.summary
            for segment in segments
            if segment.kind == "image_analysis"
        ]
        file_results = [
            segment.summary
            for segment in segments
            if segment.kind == "file"
        ]
        forward_results = [
            segment.summary
            for segment in segments
            if segment.kind == "forward_summary"
        ]
        dropped = [segment.summary for segment in replay_plan.dropped_segments]
        failures = [
            segment.summary
            for segment in segments
            if segment.kind == "image_analysis"
            and segment.metadata.get("success") == "false"
        ]
        return (
            f"QQ Official resolve summary: source={event.unified_msg_origin} "
            f"message_id={message_id or '<unknown>'} "
            f"components={component_names} "
            f"chunks={len(replay_plan.chunks)} "
            f"dropped={dropped or ['<none>']} "
            f"images={image_results or ['<none>']} "
            f"files={file_results or ['<none>']} "
            f"forwards={forward_results or ['<none>']} "
            f"failures={failures or ['<none>']}"
        )

    @staticmethod
    def _describe_image(component: Image) -> str:
        if component.url:
            return "Image resource"
        if component.file and component.file.startswith("base64://"):
            return "Image resource (base64)"
        if component.file and component.file.startswith("file://"):
            return "Image resource (file)"
        return "Image resource"

    @staticmethod
    def _join_plain_text(components: list[Plain]) -> str:
        return "".join(component.text for component in components)
