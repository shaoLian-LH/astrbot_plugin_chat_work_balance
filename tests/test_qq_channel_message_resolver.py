from __future__ import annotations

# pyright: reportMissingImports=false

import types
from typing import cast

from astrbot.core.message.components import At, Face, File, Forward, Image, Node, Nodes, Plain, Record, Reply, Video

from chat_work_balance.resolvers.qq_channel_message_resolver import QQChannelMessageResolver
from chat_work_balance.services.merged_forward_reader import MergedForwardReader
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
    def __init__(self, summary: str = "Forward summary line") -> None:
        self.summary = summary
        self.calls: list[str] = []

    async def summarize(self, component, **kwargs) -> str:
        del component
        self.calls.append(kwargs["source_label"])
        return self.summary


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
    forward_summary: str = "Forward summary line",
) -> tuple[QQChannelMessageResolver, StubResourceAnalysisService, StubMergedForwardReader]:
    analysis_service = StubResourceAnalysisService(analysis_results)
    forward_reader = StubMergedForwardReader(summary=forward_summary)
    resolver = QQChannelMessageResolver(
        merged_forward_reader=cast(MergedForwardReader, forward_reader),
        resource_analysis_service=cast(ResourceAnalysisService, analysis_service),
    )
    return resolver, analysis_service, forward_reader


def test_resolve_plain_text_keeps_original_text_and_log_context() -> None:
    resolver, _, _ = _build_resolver(analysis_results=[])
    event = FakeEvent([Plain("hello"), Plain(" world")], message_id="msg-text")

    resolved = run_async(resolver.resolve(event))

    assert [segment.kind for segment in resolved.segments] == ["plain", "plain"]
    assert len(resolved.replay_plan.chunks) == 1
    assert resolved.replay_plan.chunks[0].intent == "text"
    assert [item.text for item in resolved.replay_plan.chunks[0].chain] == ["hello", " world"]
    assert resolved.replay_plan.chunks[0].source_indexes == (0, 1)
    assert resolved.replay_plan.chunks[0].summary == "hello world"
    assert "plugin=chat_work_balance stage=message_resolved_summary" in resolved.log_summary
    assert "message_id=msg-text" in resolved.log_summary
    assert "components=['Plain', 'Plain']" in resolved.log_summary


def test_resolve_image_analysis_text_isolated_from_media_chunks() -> None:
    resolver, analysis_service, _ = _build_resolver(
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
            "unified_msg_origin": "qq_official:channel:1",
            "source_label": "message:msg-image-analysis#1",
        }
    ]


def test_resolve_multi_rich_media_enforces_single_media_intent_per_chunk() -> None:
    resolver, analysis_service, forward_reader = _build_resolver(
        analysis_results=[
            _analysis_result("Image analysis: first image"),
            _analysis_result("Image analysis: second image"),
        ],
        forward_summary="Forward summary line",
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
            "unified_msg_origin": "qq_official:channel:1",
            "source_label": "message:msg-rich#1",
        },
        {
            "unified_msg_origin": "qq_official:channel:1",
            "source_label": "message:msg-rich#5",
        },
    ]
    assert forward_reader.calls == ["forward:msg-rich#4"]


def test_resolve_forward_node_and_nodes_only_emit_summary_text() -> None:
    resolver, _, forward_reader = _build_resolver(
        analysis_results=[],
        forward_summary="Merged forward summary",
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


def test_resolve_dropped_segments_stay_observable_alongside_supported_text() -> None:
    resolver, _, _ = _build_resolver(analysis_results=[])
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
    from chat_work_balance.resolvers import qq_channel_message_resolver as resolver_module

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
    resolver, _, _ = _build_resolver(
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
