from __future__ import annotations

# pyright: reportMissingImports=false

from typing import cast

import pytest
from astrbot.core.message.components import Forward, Image, Node, Nodes, Plain

from chat_work_balance.services.merged_forward_reader import (
    ForwardTranscriptExtractionError,
    MergedForwardReader,
)
from chat_work_balance.services.resource_analysis_service import (
    ResourceAnalysisResult,
    ResourceAnalysisService,
)
from tests.helpers import FakeEvent, run_async


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


class FakeOneBotClient:
    def __init__(
        self,
        response: dict[str, object] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response or {"message": []}
        self.error = error
        self.calls: list[str] = []

    async def get_forward_msg(self, forward_id: str) -> dict[str, object]:
        self.calls.append(forward_id)
        if self.error is not None:
            raise self.error
        return self.response


class FakeOneBotActionClient:
    def __init__(
        self,
        response: dict[str, object] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response or {"message": []}
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_action(self, action: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((action, dict(kwargs)))
        if self.error is not None:
            raise self.error
        return self.response


class FakeOneBotApiClient:
    def __init__(
        self,
        response: dict[str, object] | None = None,
    ) -> None:
        self.api = FakeOneBotActionClient(response)


def _extract(
    component: Forward | Node | Nodes,
    *,
    reader: MergedForwardReader | None = None,
    event: FakeEvent | None = None,
    analysis_service: StubResourceAnalysisService | None = None,
):
    actual_reader = reader or MergedForwardReader()
    actual_analysis_service = analysis_service or StubResourceAnalysisService()
    return run_async(
        actual_reader.extract(
            component,
            event=event,
            resource_analysis_service=cast(
                ResourceAnalysisService, actual_analysis_service
            ),
            unified_msg_origin="umo",
            source_label="forward:1",
        )
    )


def test_extract_keeps_threshold_boundary_without_sampling() -> None:
    reader = MergedForwardReader(
        sample_threshold=3,
        sample_head_count=2,
        sample_tail_count=2,
    )
    component = Nodes(
        nodes=[
            Node(name="alice", content=[Plain("one")]),
            Node(name="bob", content=[Plain("two")]),
            Node(name="carol", content=[Plain("three")]),
        ]
    )

    transcript = _extract(component, reader=reader)

    assert [entry.sender_name for entry in transcript.entries] == ["alice", "bob", "carol"]
    assert [entry.text for entry in transcript.entries] == ["one", "two", "three"]
    assert transcript.notes == ()
    assert transcript.stats.total_nodes == 3
    assert transcript.stats.kept_nodes == 3
    assert transcript.stats.sampled_nodes == 0


def test_extract_samples_head_tail_without_duplicates() -> None:
    reader = MergedForwardReader(
        sample_threshold=4,
        sample_head_count=3,
        sample_tail_count=3,
    )
    component = Nodes(
        nodes=[
            Node(name=f"user-{index}", content=[Plain(f"message-{index}")])
            for index in range(5)
        ]
    )

    transcript = _extract(component, reader=reader)

    assert [entry.sender_name for entry in transcript.entries] == [
        "user-0",
        "user-1",
        "user-2",
        "user-3",
        "user-4",
    ]
    assert transcript.notes == ()
    assert transcript.stats.sampled_nodes == 0


def test_extract_applies_sampling_per_layer_independently() -> None:
    reader = MergedForwardReader(
        sample_threshold=2,
        sample_head_count=1,
        sample_tail_count=1,
    )
    component = Nodes(
        nodes=[
            Node(
                name="outer-0",
                content=[
                    Plain("o0"),
                    Nodes(
                        nodes=[
                            Node(name="inner-0", content=[Plain("i0")]),
                            Node(name="inner-1", content=[Plain("i1")]),
                            Node(name="inner-2", content=[Plain("i2")]),
                        ]
                    ),
                ],
            ),
            Node(name="outer-1", content=[Plain("o1")]),
            Node(name="outer-2", content=[Plain("o2")]),
        ]
    )

    transcript = _extract(component, reader=reader)

    assert [(entry.depth, entry.sender_name, entry.text) for entry in transcript.entries] == [
        (0, "outer-0", "o0"),
        (1, "inner-0", "i0"),
        (1, "inner-2", "i2"),
        (0, "outer-2", "o2"),
    ]
    assert [note.text for note in transcript.notes] == [
        "Skipped 1 nodes in this layer",
        "Skipped 1 nodes in this layer",
    ]
    assert transcript.stats.total_nodes == 6
    assert transcript.stats.kept_nodes == 4
    assert transcript.stats.sampled_nodes == 2


def test_extract_stops_before_nodes_beyond_max_depth() -> None:
    reader = MergedForwardReader(max_depth=3)
    component = Nodes(
        nodes=[
            Node(
                name="level-0",
                content=[
                    Plain("root"),
                    Nodes(
                        nodes=[
                            Node(
                                name="level-1",
                                content=[
                                    Plain("mid"),
                                    Nodes(
                                        nodes=[
                                            Node(
                                                name="level-2",
                                                content=[
                                                    Plain("deep"),
                                                    Nodes(
                                                        nodes=[
                                                            Node(
                                                                name="level-3",
                                                                content=[
                                                                    Plain(
                                                                        "too deep to include"
                                                                    )
                                                                ],
                                                            )
                                                        ]
                                                    ),
                                                ],
                                            )
                                        ]
                                    ),
                                ],
                            )
                        ]
                    ),
                ],
            )
        ]
    )

    transcript = _extract(component, reader=reader)

    assert [(entry.depth, entry.sender_name, entry.text) for entry in transcript.entries] == [
        (0, "level-0", "root"),
        (1, "level-1", "mid"),
        (2, "level-2", "deep"),
    ]
    assert "too deep to include" not in "\n".join(entry.text for entry in transcript.entries)
    assert transcript.stats.truncated_layers == 1


def test_extract_expands_forward_reference_and_collects_image_analysis() -> None:
    analysis_service = StubResourceAnalysisService()
    onebot_client = FakeOneBotClient(
        response={
            "message": [
                {
                    "type": "node",
                    "data": {
                        "nickname": "alice",
                        "user_id": "1001",
                        "content": [
                            {"type": "text", "data": {"text": "Status update"}},
                            {
                                "type": "image",
                                "data": {"url": "https://example.com/a.png"},
                            },
                        ],
                    }
                }
            ]
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(
        Forward(id="forward-1"),
        event=event,
        analysis_service=analysis_service,
    )

    assert onebot_client.calls == ["forward-1"]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("alice", "1001", "Status updateImage analysis: Nested chart")
    ]
    assert analysis_service.calls == [
        {"unified_msg_origin": "umo", "source_label": "forward:1:forward:forward-1:0#1"}
    ]
    assert transcript.stats.failed_forwards == 0
    assert transcript.stats.filtered_nodes == 0


def test_extract_expands_forward_reference_with_string_content() -> None:
    onebot_client = FakeOneBotClient(
        response={
            "message": [
                {
                    "type": "node",
                    "data": {
                        "nickname": "alice",
                        "user_id": "1001",
                        "content": "Status update from string payload",
                    },
                }
            ]
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-string"), event=event)

    assert onebot_client.calls == ["forward-string"]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("alice", "1001", "Status update from string payload")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 0
    assert transcript.stats.failed_forwards == 0


def test_extract_expands_forward_reference_from_data_messages_with_sender() -> None:
    onebot_client = FakeOneBotClient(
        response={
            "data": {
                "messages": [
                    {
                        "content": [
                            {"type": "text", "data": {"text": "Status from real payload"}}
                        ],
                        "sender": {
                            "nickname": "alice",
                            "user_id": 1001,
                        },
                    }
                ]
            }
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-data-messages"), event=event)

    assert onebot_client.calls == ["forward-data-messages"]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("alice", "1001", "Status from real payload")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 0
    assert transcript.stats.failed_forwards == 0


def test_extract_expands_forward_reference_from_top_level_messages() -> None:
    onebot_client = FakeOneBotClient(
        response={
            "messages": [
                {
                    "content": "Status from top-level messages",
                    "sender": {
                        "card": "team lead",
                        "uin": "1002",
                    },
                }
            ]
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-top-messages"), event=event)

    assert onebot_client.calls == ["forward-top-messages"]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("team lead", "1002", "Status from top-level messages")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 0
    assert transcript.stats.failed_forwards == 0


def test_extract_expands_forward_reference_via_direct_call_action() -> None:
    onebot_client = FakeOneBotActionClient(
        response={
            "data": {
                "messages": [
                    {
                        "message": [
                            {"type": "text", "data": {"text": "Status from call_action"}}
                        ],
                        "sender": {
                            "nickname": "alice",
                            "user_id": "1001",
                        },
                    }
                ]
            }
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-action"), event=event)

    assert onebot_client.calls == [
        ("get_forward_msg", {"message_id": "forward-action"})
    ]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("alice", "1001", "Status from call_action")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 0
    assert transcript.stats.failed_forwards == 0


def test_extract_expands_forward_reference_via_nested_api_call_action() -> None:
    onebot_client = FakeOneBotApiClient(
        response={
            "data": {
                "message": [
                    {
                        "content": [
                            {"type": "text", "data": {"text": "Status from api call_action"}}
                        ],
                        "sender": {
                            "nickname": "bob",
                            "user_id": "1002",
                        },
                    }
                ]
            }
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-api-action"), event=event)

    assert onebot_client.api.calls == [
        ("get_forward_msg", {"message_id": "forward-api-action"})
    ]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("bob", "1002", "Status from api call_action")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 0
    assert transcript.stats.failed_forwards == 0


def test_extract_expands_forward_reference_from_single_data_node() -> None:
    onebot_client = FakeOneBotActionClient(
        response={
            "data": {
                "message": [
                    {"type": "text", "data": {"text": "Status from single data node"}}
                ],
                "sender": {
                    "nickname": "carol",
                    "user_id": "1003",
                },
            }
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-single-node"), event=event)

    assert onebot_client.calls == [
        ("get_forward_msg", {"message_id": "forward-single-node"})
    ]
    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("carol", "1003", "Status from single data node")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 0
    assert transcript.stats.failed_forwards == 0


def test_extract_rejects_string_message_collection_without_iterating_characters() -> None:
    onebot_client = FakeOneBotClient(response={"message": "not-a-message-list"})
    event = FakeEvent([], onebot_client=onebot_client)

    with pytest.raises(ForwardTranscriptExtractionError) as exc_info:
        _extract(Forward(id="forward-string-collection"), event=event)

    assert str(exc_info.value) == "Merged forward transcript extraction produced no valid content."
    assert onebot_client.calls == ["forward-string-collection"]


def test_extract_counts_filtered_onebot_items_during_normalization() -> None:
    onebot_client = FakeOneBotClient(
        response={
            "message": [
                {
                    "type": "node",
                    "data": {
                        "nickname": "alice",
                        "user_id": "1001",
                        "content": [
                            {"type": "text", "data": {"text": "Status update"}},
                            {"type": "unsupported", "data": {}},
                        ],
                    },
                },
                {"type": "unsupported", "data": {}},
                {
                    "type": "node",
                    "data": {
                        "nickname": "nobody",
                        "user_id": "1002",
                        "content": [{"type": "unsupported", "data": {}}],
                    },
                },
            ]
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    transcript = _extract(Forward(id="forward-1"), event=event)

    assert [(entry.sender_name, entry.sender_id, entry.text) for entry in transcript.entries] == [
        ("alice", "1001", "Status update")
    ]
    assert transcript.stats.kept_nodes == 1
    assert transcript.stats.filtered_nodes == 4
    assert transcript.stats.failed_forwards == 0


def test_extract_counts_failed_forward_and_invalid_node_then_raises() -> None:
    onebot_client = FakeOneBotClient(error=RuntimeError("boom"))
    event = FakeEvent([], onebot_client=onebot_client)
    reader = MergedForwardReader()
    component = Nodes(nodes=[Node(name="empty", content=[]), Node(name="ref", content=[Forward(id="bad")])])

    with pytest.raises(ForwardTranscriptExtractionError) as exc_info:
        _extract(component, reader=reader, event=event)

    assert str(exc_info.value) == "Merged forward transcript extraction produced no valid content."
    assert onebot_client.calls == ["bad"]


def test_extract_raises_when_onebot_forward_contains_only_invalid_items() -> None:
    onebot_client = FakeOneBotClient(
        response={
            "message": [
                {"type": "unsupported", "data": {}},
                {
                    "type": "node",
                    "data": {
                        "nickname": "ghost",
                        "user_id": "1003",
                        "content": [{"type": "unsupported", "data": {}}],
                    },
                },
            ]
        }
    )
    event = FakeEvent([], onebot_client=onebot_client)

    with pytest.raises(ForwardTranscriptExtractionError) as exc_info:
        _extract(Forward(id="forward-invalid"), event=event)

    assert str(exc_info.value) == "Merged forward transcript extraction produced no valid content."
    assert onebot_client.calls == ["forward-invalid"]
