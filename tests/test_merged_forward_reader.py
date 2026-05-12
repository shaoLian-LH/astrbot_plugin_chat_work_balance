from __future__ import annotations

# pyright: reportMissingImports=false

from typing import cast

from astrbot.core.message.components import Image, Node, Nodes, Plain

from chat_work_balance.services.merged_forward_reader import MergedForwardReader
from chat_work_balance.services.resource_analysis_service import ResourceAnalysisService, ResourceAnalysisResult
from tests.helpers import run_async


class StubResourceAnalysisService:
    def __init__(self, text: str = "Image analysis: Nested chart") -> None:
        self.text = text
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
        return ResourceAnalysisResult(
            success=True,
            provider_id="provider-1",
            prompt="Describe",
            text=self.text,
            detail=self.text,
        )


def test_summarize_includes_nested_image_analysis() -> None:
    reader = MergedForwardReader()
    analysis_service = StubResourceAnalysisService()
    component = Nodes(
        nodes=[
            Node(
                name="alice",
                content=[Plain("Status update"), Image(url="https://example.com/a.png")],
            )
        ]
    )

    summary = run_async(
        reader.summarize(
            component,
            resource_analysis_service=cast(ResourceAnalysisService, analysis_service),
            unified_msg_origin="umo",
            source_label="forward:1#0",
        )
    )

    assert "Node from alice:" in summary
    assert "Status update" in summary
    assert "Image analysis: Nested chart" in summary
    assert analysis_service.calls == [
        {"unified_msg_origin": "umo", "source_label": "forward:1#0"}
    ]


def test_summarize_truncates_when_depth_limit_is_reached() -> None:
    reader = MergedForwardReader(max_depth=3)
    analysis_service = StubResourceAnalysisService()
    component = Nodes(
        nodes=[
            Node(
                name="level-1",
                content=[
                    Nodes(
                        nodes=[
                            Node(
                                name="level-2",
                                content=[
                                    Nodes(
                                        nodes=[
                                            Node(
                                                name="level-3",
                                                content=[Plain("too deep to include")],
                                            )
                                        ]
                                    )
                                ],
                            )
                        ]
                    )
                ],
            )
        ]
    )

    summary = run_async(
        reader.summarize(
            component,
            resource_analysis_service=cast(ResourceAnalysisService, analysis_service),
            unified_msg_origin="umo",
            source_label="forward:1#1",
        )
    )

    assert "Node from level-1:" in summary
    assert "Node from level-2:" in summary
    assert "[Max depth reached]" in summary
    assert "Forward summary truncated: max depth or node limit reached." in summary
    assert "too deep to include" not in summary
