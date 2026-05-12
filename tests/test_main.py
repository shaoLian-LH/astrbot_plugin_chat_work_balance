from __future__ import annotations

# pyright: reportMissingImports=false

import types
from typing import cast

from astrbot.core.message.components import Plain

import main
from chat_work_balance.models import ReplayChunk, ReplayPlan, ResolvedMessage
from chat_work_balance.resolvers.qq_channel_message_resolver import QQChannelMessageResolver
from tests.helpers import FakeContext, FakeEvent, collect_async, run_async


class StubResolver:
    def __init__(self, result: ResolvedMessage | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def resolve(self, event) -> ResolvedMessage:
        del event
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def test_on_message_replays_all_chunks_and_stops_event(monkeypatch) -> None:
    logger = types.SimpleNamespace(info=[], exception=[])
    monkeypatch.setattr(main, "logger", types.SimpleNamespace(
        info=lambda message: logger.info.append(message),
        exception=lambda message: logger.exception.append(message),
    ))
    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    plugin._resolver = cast(
        QQChannelMessageResolver,
        StubResolver(
        result=ResolvedMessage(
            log_summary="resolved summary",
            replay_plan=ReplayPlan(
                chunks=[
                    ReplayChunk(chain=[Plain("first")], source_indexes=(0,), summary="first"),
                    ReplayChunk(chain=[Plain("second")], source_indexes=(1,), summary="second"),
                ]
            ),
        )
        ),
    )
    event = FakeEvent([], message_id="msg-main")

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [
        {"type": "chain", "chain": [Plain("first")]},
        {"type": "chain", "chain": [Plain("second")]},
    ]
    assert event.chain_calls == [[Plain("first")], [Plain("second")]]
    assert event.stopped == 1
    assert logger.info == ["resolved summary"]
    assert logger.exception == []


def test_on_message_returns_short_error_when_resolver_raises(monkeypatch) -> None:
    logger = types.SimpleNamespace(info=[], exception=[])
    monkeypatch.setattr(main, "logger", types.SimpleNamespace(
        info=lambda message: logger.info.append(message),
        exception=lambda message: logger.exception.append(message),
    ))
    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    plugin._resolver = cast(
        QQChannelMessageResolver,
        StubResolver(error=RuntimeError("unexpected")),
    )
    event = FakeEvent([], message_id="msg-error")

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [
        {"type": "plain", "text": "Message resolver is temporarily unavailable."}
    ]
    assert event.plain_calls == ["Message resolver is temporarily unavailable."]
    assert event.stopped == 1
    assert logger.info == []
    assert logger.exception == ["Failed to resolve QQ Official message."]
