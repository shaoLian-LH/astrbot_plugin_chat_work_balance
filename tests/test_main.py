from __future__ import annotations

# pyright: reportMissingImports=false

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import cast

from astrbot.core.message.components import Plain

from chat_work_balance.models import ReplayChunk, ReplayPlan, ResolvedMessage
from chat_work_balance.resolvers.qq_channel_message_resolver import QQChannelMessageResolver
from tests.helpers import FakeContext, FakeEvent, collect_async, run_async


def _load_plugin_main_module():
    plugin_root = Path(__file__).resolve().parents[1]
    for package_name in ("data", "data.plugins"):
        if package_name not in sys.modules:
            package = types.ModuleType(package_name)
            package.__path__ = [str(plugin_root)]
            sys.modules[package_name] = package
    plugin_package_name = "data.plugins.chat_work_balance"
    if plugin_package_name not in sys.modules:
        plugin_package = types.ModuleType(plugin_package_name)
        plugin_package.__path__ = [str(plugin_root)]
        sys.modules[plugin_package_name] = plugin_package
    importlib.import_module(f"{plugin_package_name}.chat_work_balance")
    spec = importlib.util.spec_from_file_location(
        f"{plugin_package_name}.main",
        str(plugin_root / "main.py"),
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


main = _load_plugin_main_module()


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


def test_plugin_main_imports_under_package_context() -> None:
    assert main.__name__ == "data.plugins.chat_work_balance.main"
    assert main.ChatWorkBalancePlugin.__module__ == "data.plugins.chat_work_balance.main"


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
