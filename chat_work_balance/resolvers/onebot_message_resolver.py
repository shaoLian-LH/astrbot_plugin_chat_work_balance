from __future__ import annotations

# pyright: reportMissingImports=false

from typing import Iterable, Literal

from astrbot.api import logger
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
from ..services.forward_summary_service import ForwardSummaryResult, ForwardSummaryService
from ..services.merged_forward_reader import (
    ForwardTranscriptExtractionError,
    ForwardLayerNote,
    ForwardTranscriptEntry,
    MergedForwardReader,
)
from ..services.resource_analysis_service import ResourceAnalysisService

_PLUGIN_NAME = "chat_work_balance"
_FORWARD_TRANSCRIPT_FAILURE_TEXT = "Merged forward parsing failed: no readable content."


class OneBotMessageResolver:
    """Resolve full OneBot message chains into replay-safe chunks."""

    def __init__(
        self,
        merged_forward_reader: MergedForwardReader,
        forward_summary_service: ForwardSummaryService,
        resource_analysis_service: ResourceAnalysisService,
    ) -> None:
        self._merged_forward_reader = merged_forward_reader
        self._forward_summary_service = forward_summary_service
        self._resource_analysis_service = resource_analysis_service

    async def resolve(self, event: AstrMessageEvent) -> ResolvedMessage:
        message_obj = getattr(event, "message_obj", None)
        message_id = str(getattr(message_obj, "message_id", "")) or "<unknown>"
        unified_msg_origin = str(getattr(event, "unified_msg_origin", "")) or "<unknown>"
        platform = self._resolve_platform(unified_msg_origin)
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
                self._log_dropped_segment(
                    unified_msg_origin=unified_msg_origin,
                    message_id=message_id,
                    platform=platform,
                    segment=segment,
                )
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
                self._log_dropped_segment(
                    unified_msg_origin=unified_msg_origin,
                    message_id=message_id,
                    platform=platform,
                    segment=segment,
                )
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
                self._log_dropped_segment(
                    unified_msg_origin=unified_msg_origin,
                    message_id=message_id,
                    platform=platform,
                    segment=segment,
                )
                continue

            if isinstance(component, (Forward, Node, Nodes)):
                logger.info(
                    self._format_observable_log(
                        "forward_summary_started",
                        unified_msg_origin=unified_msg_origin,
                        message_id=message_id,
                        platform=platform,
                        source_index=str(index),
                        component_kind=type(component).__name__,
                    )
                )
                try:
                    transcript = await self._merged_forward_reader.extract(
                        component,
                        event=event,
                        resource_analysis_service=self._resource_analysis_service,
                        unified_msg_origin=event.unified_msg_origin,
                        source_label=f"forward:{getattr(message_obj, 'message_id', 'unknown')}#{index}",
                    )
                except ForwardTranscriptExtractionError as exc:
                    stats = getattr(exc, "stats", None)
                    logger.warning(
                        self._format_observable_log(
                            "forward_transcript_failed",
                            unified_msg_origin=unified_msg_origin,
                            message_id=message_id,
                            platform=platform,
                            source_index=str(index),
                            component_kind=type(component).__name__,
                            error_type=type(exc).__name__,
                            expanded_count=str(getattr(stats, "total_nodes", 0)),
                            filtered_count=str(getattr(stats, "filtered_nodes", 0)),
                            failed_forward_count=str(getattr(stats, "failed_forwards", 0)),
                            truncated_layers=str(getattr(stats, "truncated_layers", 0)),
                        )
                    )
                    segments.append(
                        ResolvedSegment(
                            kind="forward_summary",
                            summary=_FORWARD_TRANSCRIPT_FAILURE_TEXT,
                            payload=component,
                            source_index=index,
                            replayable=True,
                            metadata=self._build_forward_failure_metadata(),
                        )
                    )
                    append_text_chunk(_FORWARD_TRANSCRIPT_FAILURE_TEXT, source_index=index)
                    continue
                transcript_text = "\n".join(
                    self._format_transcript_entry(entry)
                    for entry in transcript.entries
                )
                if transcript.notes:
                    transcript_text = "\n".join(
                        [transcript_text, *(note.text for note in transcript.notes)]
                    ).strip()
                logger.info(
                    self._format_observable_log(
                        "forward_transcript_extracted",
                        unified_msg_origin=unified_msg_origin,
                        message_id=message_id,
                        platform=platform,
                        source_index=str(index),
                        component_kind=type(component).__name__,
                        expanded_count=str(transcript.stats.total_nodes),
                        filtered_count=str(transcript.stats.filtered_nodes),
                        sampled_count=str(transcript.stats.sampled_nodes),
                        truncated_layers=str(transcript.stats.truncated_layers),
                        failed_forward_count=str(transcript.stats.failed_forwards),
                        valid_transcript_count=str(len(transcript.entries)),
                        sample_per_layer=self._format_sample_note_depths(transcript.notes),
                    )
                )
                summary_result = await self._forward_summary_service.summarize_transcript(
                    transcript_text,
                    unified_msg_origin=event.unified_msg_origin,
                    source_label=f"forward:{getattr(message_obj, 'message_id', 'unknown')}#{index}",
                )
                logger.info(
                    self._format_observable_log(
                        "forward_summary_completed",
                        unified_msg_origin=unified_msg_origin,
                        message_id=message_id,
                        platform=platform,
                        source_index=str(index),
                        component_kind=type(component).__name__,
                        provider_id=summary_result.provider_id or "<none>",
                        llm_success=str(summary_result.success).lower(),
                        summary_length=str(len(summary_result.text)),
                    )
                )
                segments.append(
                    ResolvedSegment(
                        kind="forward_summary",
                        summary=summary_result.text,
                        payload=component,
                        source_index=index,
                        replayable=True,
                        metadata=self._build_forward_summary_metadata(transcript_text, summary_result),
                    )
                )
                append_text_chunk(summary_result.text, source_index=index)
                continue

            segment = ResolvedSegment(
                kind="unknown",
                summary=f"Unsupported component dropped: {type(component).__name__}",
                payload=component,
                source_index=index,
                replayable=False,
            )
            segments.append(segment)
            dropped_segments.append(segment)
            self._log_dropped_segment(
                unified_msg_origin=unified_msg_origin,
                message_id=message_id,
                platform=platform,
                segment=segment,
            )

        await flush_text_buffer()

        replay_plan = ReplayPlan(chunks=chunks, dropped_segments=dropped_segments)
        logger.info(
            self._format_observable_log(
                "message_resolved",
                unified_msg_origin=unified_msg_origin,
                message_id=message_id,
                platform=platform,
                component_names=",".join(type(component).__name__ for component in message_chain) or "<none>",
                segment_count=str(len(segments)),
                chunk_count=str(len(replay_plan.chunks)),
                dropped_count=str(len(replay_plan.dropped_segments)),
            )
        )
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
            self._format_forward_summary_log_field(segment)
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
            f"plugin={_PLUGIN_NAME} stage=message_resolved_summary "
            f"platform={self._resolve_platform(event.unified_msg_origin)} "
            f"unified_msg_origin={event.unified_msg_origin} "
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
    def _format_forward_summary_log_field(segment: ResolvedSegment) -> str:
        metadata = segment.metadata
        provider_id = metadata.get("provider_id") or "<none>"
        success = metadata.get("success") or "<unknown>"
        transcript_length = metadata.get("transcript_length") or "0"
        summary_length = metadata.get("summary_length") or "0"
        return (
            "forward_summary("
            f"provider_id={provider_id},"
            f"success={success},"
            f"transcript_length={transcript_length},"
            f"summary_length={summary_length},"
            f"source_index={segment.source_index}"
            ")"
        )

    @staticmethod
    def _build_forward_summary_metadata(
        transcript: str,
        summary_result: ForwardSummaryResult,
    ) -> dict[str, str]:
        return {
            "provider_id": summary_result.provider_id,
            "success": str(summary_result.success).lower(),
            "transcript_length": str(len(transcript)),
            "summary_length": str(len(summary_result.text)),
        }

    @staticmethod
    def _build_forward_failure_metadata() -> dict[str, str]:
        return {
            "provider_id": "",
            "success": "false",
            "transcript_length": "0",
            "summary_length": str(len(_FORWARD_TRANSCRIPT_FAILURE_TEXT)),
        }

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

    @staticmethod
    def _format_transcript_entry(entry: ForwardTranscriptEntry) -> str:
        sender = entry.sender_name
        if entry.sender_id:
            sender = f"{sender}({entry.sender_id})"
        return f"{'  ' * entry.depth}{sender}: {entry.text}"

    @staticmethod
    def _format_sample_note_depths(notes: tuple[ForwardLayerNote, ...]) -> str:
        if not notes:
            return "<none>"
        grouped_counts: dict[int, int] = {}
        for note in notes:
            skipped = OneBotMessageResolver._extract_skipped_count(note.text)
            grouped_counts[note.depth] = grouped_counts.get(note.depth, 0) + skipped
        return ",".join(
            f"depth{depth}:{count}"
            for depth, count in sorted(grouped_counts.items())
        )

    @staticmethod
    def _extract_skipped_count(note_text: str) -> int:
        parts = note_text.split()
        if len(parts) < 2:
            return 0
        try:
            return int(parts[1])
        except ValueError:
            return 0

    def _log_dropped_segment(
        self,
        *,
        unified_msg_origin: str,
        message_id: str,
        platform: str,
        segment: ResolvedSegment,
    ) -> None:
        logger.warning(
            self._format_observable_log(
                "dropped_segment",
                unified_msg_origin=unified_msg_origin,
                message_id=message_id,
                platform=platform,
                segment_kind=segment.kind,
                source_index=str(segment.source_index),
                detail=self._shorten(segment.summary),
            )
        )

    @staticmethod
    def _format_observable_log(
        stage: str,
        *,
        unified_msg_origin: str,
        message_id: str,
        platform: str,
        **fields: str,
    ) -> str:
        parts = [
            f"plugin={_PLUGIN_NAME}",
            f"stage={stage}",
            f"platform={platform}",
            f"unified_msg_origin={unified_msg_origin}",
            f"message_id={message_id}",
        ]
        for key, value in fields.items():
            parts.append(f"{key}={value}")
        return " ".join(parts)

    @staticmethod
    def _resolve_platform(unified_msg_origin: str) -> str:
        if not unified_msg_origin:
            return "<unknown>"
        return unified_msg_origin.split(":", 1)[0] or "<unknown>"

    @staticmethod
    def _shorten(text: str, limit: int = 160) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3]}..."
