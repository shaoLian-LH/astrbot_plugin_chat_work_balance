from __future__ import annotations

# pyright: reportMissingImports=false

import types
from typing import cast

from astrbot.core.message.components import At, Face, File, Forward, Image, Node, Nodes, Plain, Record, Reply, Video

from chat_work_balance.resolvers.onebot_message_resolver import OneBotMessageResolver
from chat_work_balance.services.forward_summary_service import ForwardSummaryResult, ForwardSummaryService
from chat_work_balance.services.merged_forward_reader import (
    ForwardLayerNote,
    ForwardTranscript,
    ForwardTranscriptEntry,
    ForwardTranscriptExtractionError,
    ForwardTranscriptStats,
    MergedForwardReader,
)
from chat_work_balance.services.resource_analysis_service import ResourceAnalysisResult, ResourceAnalysisService
from tests.helpers import FakeEvent, run_async


class StubResourceAnalysisService:
    def __init__(self, results: list[ResourceAnalysisResult]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, str]] = []

    async def analyze_image(
        self,
        image: Image,
        *,
        unified_msg_origin: str,
        source_label: str,
    ) -> ResourceAnalysisResult:
        del image
        self.calls.append(
            {"unified_msg_origin": unified_msg_origin, "source_label": source_label}
        )
        return self._results.pop(0)


class StubMergedForwardReader:
    def __init__(
        self,
        transcript: ForwardTranscript | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.transcript = transcript or ForwardTranscript(
            entries=(
                ForwardTranscriptEntry(
                    sender_name="alice",
                    sender_id="1001",
                    depth=0,
                    order=0,
                    text="Forward transcript line",
                ),
            ),
            notes=(),
            stats=ForwardTranscriptStats(total_nodes=1, kept_nodes=1),
        )
        self.error = error
        self.calls: list[str] = []

    async def extract(self, component, **kwargs) -> ForwardTranscript:
        del component
        self.calls.append(kwargs["source_label"])
        if self.error is not None:
            raise self.error
        return self.transcript


class StubForwardSummaryService:
    def __init__(
        self,
        result: ForwardSummaryResult | None = None,
    ) -> None:
        self.result = result or ForwardSummaryResult(
            success=True,
            provider_id="provider-1",
            prompt="Prompt",
            text="Forward summary line",
            detail="Forward summary line",
        )
        self.calls: list[dict[str, str]] = []

    async def summarize_transcript(
        self,
        transcript: str,
        *,
        unified_msg_origin: str,
        source_label: str,
    ) -> ForwardSummaryResult:
        self.calls.append(
            {
                "transcript": transcript,
                "unified_msg_origin": unified_msg_origin,
                "source_label": source_label,
            }
        )
        return self.result


def _analysis_result(text: str, *, success: bool = True) -> ResourceAnalysisResult:
    return ResourceAnalysisResult(
        success=success,
        provider_id="provider-1",
        prompt="Describe",
        text=text,
        detail=text,
    )


def _build_resolver(
    *,
    analysis_results: list[ResourceAnalysisResult],
    forward_summary_result: ForwardSummaryResult | None = None,
    forward_transcript: ForwardTranscript | None = None,
    forward_error: Exception | None = None,
) -> tuple[
    OneBotMessageResolver,
    StubResourceAnalysisService,
    StubMergedForwardReader,
    StubForwardSummaryService,
]:
    analysis_service = StubResourceAnalysisService(analysis_results)
    forward_reader = StubMergedForwardReader(
        transcript=forward_transcript,
        error=forward_error,
    )
    forward_summary_service = StubForwardSummaryService(result=forward_summary_result)
    resolver = OneBotMessageResolver(
        merged_forward_reader=cast(MergedForwardReader, forward_reader),
        forward_summary_service=cast(ForwardSummaryService, forward_summary_service),
        resource_analysis_service=cast(ResourceAnalysisService, analysis_service),
    )
    return resolver, analysis_service, forward_reader, forward_summary_service


def test_resolve_plain_text_keeps_original_text_and_log_context() -> None:
    resolver, _, _, _ = _build_resolver(analysis_results=[])
    event = FakeEvent([Plain("hello"), Plain(" world")], message_id="msg-text")

    resolved = run_async(resolver.resolve(event))

    assert [segment.kind for segment in resolved.segments] == ["plain", "plain"]
    assert len(resolved.replay_plan.chunks) == 1
    assert resolved.replay_plan.chunks[0].intent == "text"
    assert [item.text for item in resolved.replay_plan.chunks[0].chain] == ["hello", " world"]
    assert resolved.replay_plan.chunks[0].source_indexes == (0, 1)
    assert resolved.replay_plan.chunks[0].summary == "hello world"
    assert "plugin=chat_work_balance stage=message_resolved_summary" in resolved.log_summary
    assert "platform=aiocqhttp" in resolved.log_summary
    assert "unified_msg_origin=aiocqhttp:group:1" in resolved.log_summary
    assert "message_id=msg-text" in resolved.log_summary
    assert "components=['Plain', 'Plain']" in resolved.log_summary


def test_resolve_image_analysis_text_isolated_from_media_chunks() -> None:
    resolver, analysis_service, _, _ = _build_resolver(
        analysis_results=[_analysis_result("Image analysis: Whiteboard summary")]
    )
    event = FakeEvent(
        [
            Plain("before"),
            Image(url="https://example.com/whiteboard.png"),
            Plain("after"),
        ],
        message_id="msg-image-analysis",
    )

    resolved = run_async(resolver.resolve(event))

    assert [segment.kind for segment in resolved.segments] == [
        "plain",
        "image",
        "image_analysis",
        "plain",
    ]
    assert [(chunk.intent, chunk.summary) for chunk in resolved.replay_plan.chunks] == [
        ("text", "before"),
        ("image", "Image resource"),
        ("text", "Image analysis: Whiteboard summaryafter"),
    ]
    assert resolved.replay_plan.chunks[1].source_indexes == (1,)
    assert resolved.replay_plan.chunks[2].source_indexes == (1, 2)
    assert [type(item).__name__ for item in resolved.replay_plan.chunks[2].chain] == [
        "Plain",
        "Plain",
    ]
    assert analysis_service.calls == [
        {
            "unified_msg_origin": "aiocqhttp:group:1",
            "source_label": "message:msg-image-analysis#1",
        }
    ]


def test_resolve_multi_rich_media_enforces_single_media_intent_per_chunk() -> None:
    resolver, analysis_service, forward_reader, _ = _build_resolver(
        analysis_results=[
            _analysis_result("Image analysis: first image"),
            _analysis_result("Image analysis: second image"),
        ],
        forward_summary_result=ForwardSummaryResult(
            success=True,
            provider_id="provider-1",
            prompt="Prompt",
            text="Forward summary line",
            detail="Forward summary line",
        ),
    )
    event = FakeEvent(
        [
            Plain("alpha"),
            Image(url="https://example.com/1.png"),
            File(name="first.txt", get_file_result="https://files.example.com/first.txt"),
            Plain("beta"),
            Nodes(nodes=[]),
            Image(url="https://example.com/2.png"),
            Record(file="/tmp/audio.wav"),
            Video(file="/tmp/video.mp4"),
            File(name="second.txt", get_file_result="/tmp/second.txt"),
            Plain("omega"),
        ],
        message_id="msg-rich",
    )

    resolved = run_async(resolver.resolve(event))

    assert [(chunk.intent, chunk.summary) for chunk in resolved.replay_plan.chunks] == [
        ("text", "alpha"),
        ("image", "Image resource"),
        ("text", "Image analysis: first image"),
        ("file", "File: first.txt (url)"),
        ("text", "betaForward summary line"),
        ("image", "Image resource"),
        ("text", "Image analysis: second image"),
        ("record", "Voice message"),
        ("video", "Video message"),
        ("file", "File: second.txt (path)"),
        ("text", "omega"),
    ]
    assert [chunk.source_indexes for chunk in resolved.replay_plan.chunks] == [
        (0,),
        (1,),
        (1,),
        (2,),
        (3, 4),
        (5,),
        (5,),
        (6,),
        (7,),
        (8,),
        (9,),
    ]
    assert [type(chunk.chain[0]).__name__ for chunk in resolved.replay_plan.chunks[1:10:2]] == [
        "Image",
        "File",
        "Image",
        "Record",
        "File",
    ]
    assert analysis_service.calls == [
        {
            "unified_msg_origin": "aiocqhttp:group:1",
            "source_label": "message:msg-rich#1",
        },
        {
            "unified_msg_origin": "aiocqhttp:group:1",
            "source_label": "message:msg-rich#5",
        },
    ]
    assert forward_reader.calls == ["forward:msg-rich#4"]


def test_resolve_forward_node_and_nodes_only_emit_summary_text() -> None:
    transcript = ForwardTranscript(
        entries=(
            ForwardTranscriptEntry(
                sender_name="alice",
                sender_id="1001",
                depth=0,
                order=0,
                text="nested",
            ),
        ),
        notes=(ForwardLayerNote(depth=1, text="Skipped 2 nodes in this layer"),),
        stats=ForwardTranscriptStats(
            total_nodes=3,
            kept_nodes=1,
            sampled_nodes=2,
            filtered_nodes=1,
            truncated_layers=0,
            failed_forwards=0,
        ),
    )
    resolver, _, forward_reader, forward_summary_service = _build_resolver(
        analysis_results=[],
        forward_summary_result=ForwardSummaryResult(
            success=True,
            provider_id="provider-9",
            prompt="Prompt",
            text="Merged forward summary",
            detail="Merged forward summary",
        ),
        forward_transcript=transcript,
    )
    event = FakeEvent(
        [
            Forward(id="forward-1"),
            Node(name="alice", uin="1001", content=[Plain("nested")]),
            Nodes(nodes=[Node(name="bob", uin="1002", content=[Plain("more")])]),
        ],
        message_id="msg-forward",
    )

    resolved = run_async(resolver.resolve(event))

    assert [segment.kind for segment in resolved.segments] == [
        "forward_summary",
        "forward_summary",
        "forward_summary",
    ]
    assert len(resolved.replay_plan.chunks) == 1
    assert resolved.replay_plan.chunks[0].intent == "text"
    assert resolved.replay_plan.chunks[0].summary == (
        "Merged forward summaryMerged forward summaryMerged forward summary"
    )
    assert resolved.replay_plan.chunks[0].source_indexes == (0, 1, 2)
    assert [type(item).__name__ for item in resolved.replay_plan.chunks[0].chain] == [
        "Plain",
        "Plain",
        "Plain",
    ]
    assert forward_reader.calls == [
        "forward:msg-forward#0",
        "forward:msg-forward#1",
        "forward:msg-forward#2",
    ]
    assert forward_summary_service.calls == [
        {
            "transcript": "alice(1001): nested\nSkipped 2 nodes in this layer",
            "unified_msg_origin": "aiocqhttp:group:1",
            "source_label": "forward:msg-forward#0",
        },
        {
            "transcript": "alice(1001): nested\nSkipped 2 nodes in this layer",
            "unified_msg_origin": "aiocqhttp:group:1",
            "source_label": "forward:msg-forward#1",
        },
        {
            "transcript": "alice(1001): nested\nSkipped 2 nodes in this layer",
            "unified_msg_origin": "aiocqhttp:group:1",
            "source_label": "forward:msg-forward#2",
        },
    ]
    assert resolved.segments[0].metadata == {
        "provider_id": "provider-9",
        "success": "true",
        "transcript_length": "49",
        "summary_length": "22",
    }


def test_resolve_dropped_segments_stay_observable_alongside_supported_text() -> None:
    resolver, _, _, _ = _build_resolver(analysis_results=[])
    event = FakeEvent(
        [
            Plain("hello"),
            At(qq="12345"),
            Face(id="88"),
            Reply(id="reply-1"),
            Plain(" world"),
        ],
        message_id="msg-dropped",
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    from chat_work_balance.resolvers import onebot_message_resolver as resolver_module

    original_logger = resolver_module.logger
    resolver_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )
    try:
        resolved = run_async(resolver.resolve(event))
    finally:
        resolver_module.logger = original_logger

    assert [segment.kind for segment in resolved.segments] == [
        "plain",
        "at",
        "face",
        "reply",
        "plain",
    ]
    assert [segment.replayable for segment in resolved.segments] == [True, False, False, False, True]
    assert [segment.kind for segment in resolved.replay_plan.dropped_segments] == [
        "at",
        "face",
        "reply",
    ]
    assert [segment.summary for segment in resolved.replay_plan.dropped_segments] == [
        "At mention skipped: 12345",
        "Face emoji skipped in replay.",
        "Reply reference skipped: reply-1",
    ]
    assert len(resolved.replay_plan.chunks) == 1
    assert resolved.replay_plan.chunks[0].intent == "text"
    assert resolved.replay_plan.chunks[0].summary == "hello world"
    assert resolved.replay_plan.chunks[0].source_indexes == (0, 4)
    assert "dropped=['At mention skipped: 12345', 'Face emoji skipped in replay.', 'Reply reference skipped: reply-1']" in resolved.log_summary
    assert len(log_recorder.warning) == 3
    assert all("stage=dropped_segment" in message for message in log_recorder.warning)
    assert any("segment_kind=at" in message and "message_id=msg-dropped" in message for message in log_recorder.warning)
    assert any("segment_kind=face" in message for message in log_recorder.warning)
    assert any("segment_kind=reply" in message for message in log_recorder.warning)
    assert len(log_recorder.info) == 1
    assert "stage=message_resolved" in log_recorder.info[0]
    assert "dropped_count=3" in log_recorder.info[0]


def test_resolve_image_failure_still_replays_image_and_following_file() -> None:
    resolver, _, _, _ = _build_resolver(
        analysis_results=[
            _analysis_result("Image analysis failed during provider call.", success=False)
        ]
    )
    event = FakeEvent(
        [
            Image(url="https://example.com/problem.png"),
            File(name="report.txt", get_file_result="/tmp/report.txt"),
        ],
        message_id="msg-failure",
    )

    resolved = run_async(resolver.resolve(event))

    assert [(chunk.intent, chunk.summary) for chunk in resolved.replay_plan.chunks] == [
        ("image", "Image resource"),
        ("text", "Image analysis failed during provider call."),
        ("file", "File: report.txt (path)"),
    ]
    assert resolved.replay_plan.chunks[1].source_indexes == (0,)
    assert resolved.segments[1].metadata["success"] == "false"
    file_chunk = resolved.replay_plan.chunks[2]
    assert file_chunk.chain[0].file == "/tmp/report.txt"


def test_resolve_forward_summary_failure_replays_failure_text_and_logs_stats() -> None:
    transcript = ForwardTranscript(
        entries=(
            ForwardTranscriptEntry(
                sender_name="alice",
                sender_id="1001",
                depth=0,
                order=0,
                text="Launch tomorrow",
            ),
            ForwardTranscriptEntry(
                sender_name="bob",
                sender_id="1002",
                depth=1,
                order=1,
                text="Need rollback plan",
            ),
        ),
        notes=(
            ForwardLayerNote(depth=0, text="Skipped 1 nodes in this layer"),
            ForwardLayerNote(depth=1, text="Skipped 2 nodes in this layer"),
        ),
        stats=ForwardTranscriptStats(
            total_nodes=5,
            kept_nodes=2,
            sampled_nodes=3,
            filtered_nodes=1,
            truncated_layers=1,
            failed_forwards=0,
        ),
    )
    resolver, _, _, _ = _build_resolver(
        analysis_results=[],
        forward_transcript=transcript,
        forward_summary_result=ForwardSummaryResult(
            success=False,
            provider_id="provider-2",
            prompt="Prompt",
            text="转发总结失败：消息解析模型连续 3 次未返回有效摘要。",
            detail="转发总结失败：消息解析模型连续 3 次未返回有效摘要。",
        ),
    )
    event = FakeEvent([Forward(id="forward-1")], message_id="msg-forward-failure")
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    from chat_work_balance.resolvers import onebot_message_resolver as resolver_module

    original_logger = resolver_module.logger
    resolver_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )
    try:
        resolved = run_async(resolver.resolve(event))
    finally:
        resolver_module.logger = original_logger

    assert [segment.kind for segment in resolved.segments] == ["forward_summary"]
    assert resolved.replay_plan.chunks[0].intent == "text"
    assert resolved.replay_plan.chunks[0].summary == "转发总结失败：消息解析模型连续 3 次未返回有效摘要。"
    assert resolved.segments[0].metadata["provider_id"] == "provider-2"
    assert resolved.segments[0].metadata["success"] == "false"
    assert any("stage=forward_summary_started" in message for message in log_recorder.info)
    assert any(
        "stage=forward_transcript_extracted" in message
        and "expanded_count=5" in message
        and "filtered_count=1" in message
        and "sampled_count=3" in message
        and "sample_per_layer=depth0:1,depth1:2" in message
        and "valid_transcript_count=2" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=forward_summary_completed" in message
        and "provider_id=provider-2" in message
        and "llm_success=false" in message
        for message in log_recorder.info
    )
    assert "forwards=['forward_summary(provider_id=provider-2,success=false,transcript_length=120,summary_length=27,source_index=0)']" in resolved.log_summary
    assert all("Launch tomorrow" not in message for message in log_recorder.info)
    assert "Launch tomorrow" not in resolved.log_summary
    assert "Need rollback plan" not in resolved.log_summary
    assert "转发总结失败：消息解析模型连续 3 次未返回有效摘要。" not in resolved.log_summary


def test_resolve_forward_summary_log_summary_does_not_leak_transcript_or_summary_body() -> None:
    transcript = ForwardTranscript(
        entries=(
            ForwardTranscriptEntry(
                sender_name="alice",
                sender_id="1001",
                depth=0,
                order=0,
                text="Secret launch note",
            ),
        ),
        notes=(),
        stats=ForwardTranscriptStats(total_nodes=1, kept_nodes=1),
    )
    resolver, _, _, _ = _build_resolver(
        analysis_results=[],
        forward_transcript=transcript,
        forward_summary_result=ForwardSummaryResult(
            success=True,
            provider_id="provider-9",
            prompt="Prompt",
            text="Summary keeps key quote: Secret launch note",
            detail="Summary keeps key quote: Secret launch note",
        ),
    )
    event = FakeEvent([Forward(id="forward-redacted")], message_id="msg-forward-redacted")

    resolved = run_async(resolver.resolve(event))

    assert "forwards=['forward_summary(provider_id=provider-9,success=true,transcript_length=31,summary_length=43,source_index=0)']" in resolved.log_summary
    assert "Secret launch note" not in resolved.log_summary
    assert "Summary keeps key quote" not in resolved.log_summary


def test_resolve_forward_extraction_error_replays_failure_text_without_summary_call() -> None:
    resolver, _, forward_reader, forward_summary_service = _build_resolver(
        analysis_results=[],
        forward_error=ForwardTranscriptExtractionError(
            "Merged forward transcript extraction produced no valid content."
        ),
    )
    event = FakeEvent([Forward(id="forward-1")], message_id="msg-forward-empty")
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    from chat_work_balance.resolvers import onebot_message_resolver as resolver_module

    original_logger = resolver_module.logger
    resolver_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )
    try:
        resolved = run_async(resolver.resolve(event))
    finally:
        resolver_module.logger = original_logger

    assert forward_reader.calls == ["forward:msg-forward-empty#0"]
    assert forward_summary_service.calls == []
    assert [segment.kind for segment in resolved.segments] == ["forward_summary"]
    assert resolved.replay_plan.chunks[0].intent == "text"
    assert resolved.replay_plan.chunks[0].summary == "Merged forward parsing failed: no readable content."
    assert resolved.segments[0].metadata == {
        "provider_id": "",
        "success": "false",
        "transcript_length": "0",
        "summary_length": "51",
    }
    assert any(
        "stage=forward_transcript_failed" in message
        and "error_type=ForwardTranscriptExtractionError" in message
        and "source_index=0" in message
        and "component_kind=Forward" in message
        for message in log_recorder.warning
    )
    assert not any("stage=forward_summary_completed" in message for message in log_recorder.info)
