from __future__ import annotations

# pyright: reportMissingImports=false

from typing import cast

from astrbot.core.message.components import File, Image, Nodes, Plain

from chat_work_balance.resolvers.qq_channel_message_resolver import QQChannelMessageResolver
from chat_work_balance.services.merged_forward_reader import MergedForwardReader
from chat_work_balance.services.resource_analysis_service import ResourceAnalysisService, ResourceAnalysisResult
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


def test_resolve_plain_text_keeps_original_text_and_log_context() -> None:
    resolver = QQChannelMessageResolver(
        merged_forward_reader=cast(MergedForwardReader, StubMergedForwardReader()),
        resource_analysis_service=cast(ResourceAnalysisService, StubResourceAnalysisService([])),
    )
    event = FakeEvent([Plain("hello"), Plain(" world")], message_id="msg-text")

    resolved = run_async(resolver.resolve(event))

    assert [segment.kind for segment in resolved.segments] == ["plain", "plain"]
    assert len(resolved.replay_plan.chunks) == 1
    assert [item.text for item in resolved.replay_plan.chunks[0].chain] == ["hello", " world"]
    assert resolved.replay_plan.chunks[0].summary == "hello world"
    assert "message_id=msg-text" in resolved.log_summary
    assert "components=['Plain', 'Plain']" in resolved.log_summary


def test_resolve_plain_image_file_preserves_order_and_async_file_fetch() -> None:
    resolver = QQChannelMessageResolver(
        merged_forward_reader=cast(MergedForwardReader, StubMergedForwardReader()),
        resource_analysis_service=cast(
            ResourceAnalysisService,
            StubResourceAnalysisService(
                [_analysis_result("Image analysis: Whiteboard summary")]
            ),
        ),
    )
    event = FakeEvent(
        [
            Plain("before"),
            Image(url="https://example.com/whiteboard.png"),
            File(name="plan.pdf", get_file_result="https://files.example.com/plan.pdf"),
        ],
        message_id="msg-mixed",
    )

    resolved = run_async(resolver.resolve(event))

    assert [segment.kind for segment in resolved.segments] == [
        "plain",
        "image",
        "image_analysis",
        "file",
    ]
    assert [chunk.summary for chunk in resolved.replay_plan.chunks] == [
        "before",
        "Image resource",
        "Image analysis: Whiteboard summary",
        "File: plan.pdf (url)",
    ]
    assert resolved.replay_plan.chunks[2].source_indexes == (1,)
    file_chunk = resolved.replay_plan.chunks[3]
    assert isinstance(file_chunk.chain[0], File)
    assert file_chunk.chain[0].url == "https://files.example.com/plan.pdf"
    assert file_chunk.chain[0].name == "plan.pdf"


def test_resolve_image_failure_still_replays_image_and_following_file() -> None:
    resolver = QQChannelMessageResolver(
        merged_forward_reader=cast(MergedForwardReader, StubMergedForwardReader()),
        resource_analysis_service=cast(
            ResourceAnalysisService,
            StubResourceAnalysisService(
                [_analysis_result("Image analysis failed during provider call.", success=False)]
            ),
        ),
    )
    event = FakeEvent(
        [
            Image(url="https://example.com/problem.png"),
            File(name="report.txt", get_file_result="/tmp/report.txt"),
        ],
        message_id="msg-failure",
    )

    resolved = run_async(resolver.resolve(event))

    assert [chunk.summary for chunk in resolved.replay_plan.chunks] == [
        "Image resource",
        "Image analysis failed during provider call.",
        "File: report.txt (path)",
    ]
    assert resolved.segments[1].metadata["success"] == "false"
    file_chunk = resolved.replay_plan.chunks[2]
    assert file_chunk.chain[0].file == "/tmp/report.txt"


def test_resolve_multi_rich_media_splits_each_chunk_and_inlines_forward_summary() -> None:
    resolver = QQChannelMessageResolver(
        merged_forward_reader=cast(
            MergedForwardReader,
            StubMergedForwardReader(summary="Forward summary line"),
        ),
        resource_analysis_service=cast(
            ResourceAnalysisService,
            StubResourceAnalysisService(
                [
                    _analysis_result("Image analysis: first image"),
                    _analysis_result("Image analysis: second image"),
                ]
            ),
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
            File(name="second.txt", get_file_result="/tmp/second.txt"),
            Plain("omega"),
        ],
        message_id="msg-rich",
    )

    resolved = run_async(resolver.resolve(event))

    assert [chunk.summary for chunk in resolved.replay_plan.chunks] == [
        "alpha",
        "Image resource",
        "Image analysis: first image",
        "File: first.txt (url)",
        "betaForward summary line",
        "Image resource",
        "Image analysis: second image",
        "File: second.txt (path)",
        "omega",
    ]
    assert resolved.replay_plan.chunks[4].source_indexes == (3, 4)
