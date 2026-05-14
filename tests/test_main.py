from __future__ import annotations

# pyright: reportMissingImports=false

import ast
import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import cast

from astrbot.api.event import filter as event_filter
from astrbot.core.message.components import Forward, Image, Plain

from chat_work_balance.config import ChatWorkBalanceConfig
from chat_work_balance.models import ReplayChunk, ReplayPlan, ResolvedMessage
from chat_work_balance.resolvers.onebot_message_resolver import OneBotMessageResolver
from chat_work_balance.services.forward_summary_service import ForwardSummaryService
from chat_work_balance.services.merged_forward_reader import MergedForwardReader
from chat_work_balance.services.resource_analysis_service import (
    ResourceAnalysisResult,
    ResourceAnalysisService,
)
from tests.helpers import FakeContext, FakeEvent, FakeProvider, collect_async, run_async

setattr(event_filter.PlatformAdapterType, "AIOCQHTTP", "aiocqhttp")


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
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _make_async_result(result):
    async def _runner(*args, **kwargs):
        del args, kwargs
        return result

    return _runner


def _make_async_raise(error: Exception):
    async def _runner(*args, **kwargs):
        del args, kwargs
        raise error

    return _runner


def _patch_runtime_loggers(plugin, monkeypatch, shared_logger) -> None:
    resolver_module = sys.modules[plugin._resolver.__class__.__module__]
    forward_summary_module = sys.modules[
        plugin._resolver._forward_summary_service.__class__.__module__
    ]
    resource_analysis_module = sys.modules[
        plugin._resolver._resource_analysis_service.__class__.__module__
    ]
    monkeypatch.setattr(resolver_module, "logger", shared_logger)
    monkeypatch.setattr(forward_summary_module, "logger", shared_logger, raising=False)
    monkeypatch.setattr(resource_analysis_module, "logger", shared_logger, raising=False)


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


class StubResourceAnalysisService:
    async def analyze_image(
        self,
        image,
        *,
        unified_msg_origin: str,
        source_label: str,
    ) -> ResourceAnalysisResult:
        del image, unified_msg_origin, source_label
        return ResourceAnalysisResult(
            success=True,
            provider_id="provider-1",
            prompt="Describe",
            text="Image analysis: unused",
            detail="unused",
        )


class StubMergedForwardReader:
    async def extract(self, component, **kwargs):
        del component, kwargs
        raise AssertionError("extract should not be called in this stubbed resolver test")


class StubForwardSummaryService:
    async def summarize_transcript(
        self,
        transcript: str,
        *,
        unified_msg_origin: str,
        source_label: str,
    ):
        del transcript, unified_msg_origin, source_label
        return None


def test_plugin_main_imports_under_package_context() -> None:
    assert main.__name__ == "data.plugins.chat_work_balance.main"
    assert main.ChatWorkBalancePlugin.__module__ == "data.plugins.chat_work_balance.main"


def test_on_message_registers_aiocqhttp_platform_filter() -> None:
    module_ast = ast.parse((PLUGIN_ROOT / "main.py").read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in module_ast.body
        if isinstance(node, ast.ClassDef) and node.name == "ChatWorkBalancePlugin"
    )
    on_message_node = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_message"
    )
    platform_decorator = next(
        decorator
        for decorator in on_message_node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "platform_adapter_type"
    )
    platform_argument = platform_decorator.args[0]

    assert ast.unparse(platform_argument) == "filter.PlatformAdapterType.AIOCQHTTP"


def test_metadata_declares_aiocqhttp_support() -> None:
    metadata_lines = (PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines()
    support_platforms = [
        line.strip()[2:]
        for line in metadata_lines
        if line.startswith("  - ")
    ]

    assert support_platforms == ["aiocqhttp"]


def test_on_message_replays_all_chunks_and_stops_group_event(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], exception=[])
    monkeypatch.setattr(
        main,
        "logger",
        types.SimpleNamespace(
            info=lambda message: log_recorder.info.append(message),
            exception=lambda message: log_recorder.exception.append(message),
        ),
    )
    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    plugin._resolver = cast(
        OneBotMessageResolver,
        StubResolver(
            result=ResolvedMessage(
                log_summary=(
                    "plugin=chat_work_balance stage=message_resolved_summary "
                    "platform=aiocqhttp unified_msg_origin=aiocqhttp:group:1 "
                    "message_id=msg-main"
                ),
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
    assert any("stage=plugin_init" in message for message in log_recorder.info)
    assert any("stage=message_received" in message and "message_id=msg-main" in message for message in log_recorder.info)
    assert any("stage=message_resolved_summary" in message and "message_id=msg-main" in message for message in log_recorder.info)
    assert any("stage=chunk_replayed" in message and "chunk_index=0" in message for message in log_recorder.info)
    assert any("stage=chunk_replayed" in message and "chunk_index=1" in message for message in log_recorder.info)
    assert any("stage=message_completed" in message and "chunk_count=2" in message for message in log_recorder.info)
    assert log_recorder.exception == []


def test_on_message_success_path_includes_real_resolver_stage_logs(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], warning=[], exception=[])
    shared_logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
        exception=lambda message: log_recorder.exception.append(message),
    )
    monkeypatch.setattr(main, "logger", shared_logger)
    provider = FakeProvider(completion_text="Desk photo")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_image_caption_provider_id": "provider-1",
                "image_caption_prompt": "Describe the image",
            }
        },
        providers={"provider-1": provider},
    )
    plugin = main.ChatWorkBalancePlugin(context, {})
    plugin._resolver = OneBotMessageResolver(
        merged_forward_reader=cast(MergedForwardReader, StubMergedForwardReader()),
        forward_summary_service=cast(ForwardSummaryService, StubForwardSummaryService()),
        resource_analysis_service=ResourceAnalysisService(
            context=context,
            plugin_config=ChatWorkBalanceConfig(),
        ),
    )
    _patch_runtime_loggers(plugin, monkeypatch, shared_logger)
    image = Image(file_path="/tmp/desk.png")
    event = FakeEvent([Plain("hello"), image, Plain(" world")], message_id="msg-real")

    results = run_async(collect_async(plugin.on_message(event)))

    assert len(results) == 3
    first_result = cast(dict[str, object], results[0])
    second_result = cast(dict[str, object], results[1])
    third_result = cast(dict[str, object], results[2])
    assert first_result["type"] == "chain"
    assert second_result["type"] == "chain"
    assert third_result["type"] == "chain"
    assert [item.text for item in cast(list[Plain], first_result["chain"])] == ["hello"]
    assert cast(list[object], second_result["chain"]) == [image]
    assert [item.text for item in cast(list[Plain], third_result["chain"])] == [
        "Image analysis: Desk photo",
        " world",
    ]
    assert len(event.chain_calls) == 3
    assert [item.text for item in cast(list[Plain], event.chain_calls[0])] == ["hello"]
    assert cast(list[object], event.chain_calls[1]) == [image]
    assert [item.text for item in cast(list[Plain], event.chain_calls[2])] == [
        "Image analysis: Desk photo",
        " world",
    ]
    assert event.stopped == 1
    assert provider.calls == [
        {
            "prompt": "Describe the image",
            "image_urls": ["file:///tmp/desk.png"],
        }
    ]
    assert any("stage=plugin_init" in message for message in log_recorder.info)
    assert any("stage=message_received" in message and "message_id=msg-real" in message for message in log_recorder.info)
    assert any("stage=message_resolved " in message and "message_id=msg-real" in message for message in log_recorder.info)
    assert any("stage=provider_succeeded" in message and "message_id=msg-real" in message for message in log_recorder.info)
    assert any(
        "stage=chunk_replayed" in message
        and "message_id=msg-real" in message
        and "chunk_index=0" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=chunk_replayed" in message
        and "message_id=msg-real" in message
        and "chunk_index=1" in message
        and "chunk_intent=image" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=chunk_replayed" in message
        and "message_id=msg-real" in message
        and "chunk_index=2" in message
        and "chunk_summary=Image analysis: Desk photo world" in message
        for message in log_recorder.info
    )
    assert any("stage=message_completed" in message and "message_id=msg-real" in message for message in log_recorder.info)
    assert log_recorder.warning == []
    assert log_recorder.exception == []


def test_plugin_init_wires_forward_dependencies_from_plugin_config() -> None:
    plugin = main.ChatWorkBalancePlugin(
        FakeContext(),
        {
            "forward_max_depth": 5,
            "forward_sample_threshold": 9,
            "forward_sample_head_count": 4,
            "forward_sample_tail_count": 3,
        },
    )

    assert plugin._resolver._merged_forward_reader._max_depth == 5
    assert plugin._resolver._merged_forward_reader._sample_threshold == 9
    assert plugin._resolver._merged_forward_reader._sample_head_count == 4
    assert plugin._resolver._merged_forward_reader._sample_tail_count == 3
    assert plugin._resolver._forward_summary_service.__class__.__name__ == "ForwardSummaryService"


def test_on_message_forward_summary_replays_group_chain_and_logs_without_transcript_leak(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], warning=[], exception=[])
    shared_logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
        exception=lambda message: log_recorder.exception.append(message),
    )
    monkeypatch.setattr(main, "logger", shared_logger)

    provider = FakeProvider(completion_text="张三：明天灰度；李四：补回滚预案。")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "message-provider",
            }
        },
        providers={"message-provider": provider},
    )
    plugin = main.ChatWorkBalancePlugin(context, {})
    _patch_runtime_loggers(plugin, monkeypatch, shared_logger)
    event = FakeEvent(
        [Forward(id="forward-1")],
        message_id="msg-forward-main",
        onebot_client=types.SimpleNamespace(
            get_forward_msg=_make_async_result(
                {
                    "message": [
                        {
                            "type": "node",
                            "data": {
                                "nickname": "alice",
                                "user_id": "1001",
                                "content": [{"type": "text", "data": {"text": "明天灰度"}}],
                            },
                        },
                        {
                            "type": "node",
                            "data": {
                                "nickname": "bob",
                                "user_id": "1002",
                                "content": [{"type": "text", "data": {"text": "需要回滚预案"}}],
                            },
                        },
                    ]
                }
            )
        ),
    )

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [{"type": "chain", "chain": [Plain("张三：明天灰度；李四：补回滚预案。")]}]
    assert event.chain_calls == [[Plain("张三：明天灰度；李四：补回滚预案。")]]
    assert event.stopped == 1
    assert provider.calls and provider.calls[0]["image_urls"] == []
    assert any("stage=forward_summary_started" in message and "message_id=msg-forward-main" in message for message in log_recorder.info)
    assert any(
        "stage=forward_transcript_extracted" in message
        and "message_id=msg-forward-main" in message
        and "expanded_count=2" in message
        and "filtered_count=0" in message
        and "valid_transcript_count=2" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=provider_succeeded" in message
        and "message_id=msg-forward-main" in message
        and "provider_id=message-provider" in message
        and "summary_length=17" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=forward_summary_completed" in message
        and "message_id=msg-forward-main" in message
        and "llm_success=true" in message
        and "summary_length=17" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=message_resolved_summary" in message
        and "forwards=['forward_summary(provider_id=message-provider,success=true,transcript_length=35,summary_length=17,source_index=0)']" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=chunk_replayed" in message
        and "message_id=msg-forward-main" in message
        and "chunk_source=forward_summary" in message
        and "chunk_summary_length=17" in message
        and "chunk_summary=" not in message
        for message in log_recorder.info
    )
    assert all("明天灰度" not in message for message in log_recorder.info)
    assert all("需要回滚预案" not in message for message in log_recorder.info)
    assert all("张三：明天灰度；李四：补回滚预案。" not in message for message in log_recorder.info)


def test_on_message_forward_summary_replays_private_chain_when_provider_returns_failure_text(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], warning=[], exception=[])
    shared_logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
        exception=lambda message: log_recorder.exception.append(message),
    )
    monkeypatch.setattr(main, "logger", shared_logger)

    context = FakeContext(global_config={"provider_settings": {}}, providers={})
    plugin = main.ChatWorkBalancePlugin(context, {})
    _patch_runtime_loggers(plugin, monkeypatch, shared_logger)
    event = FakeEvent(
        [Forward(id="forward-2")],
        message_id="msg-forward-private",
        unified_msg_origin="aiocqhttp:private:1",
        onebot_client=types.SimpleNamespace(
            get_forward_msg=_make_async_result(
                {
                    "message": [
                        {
                            "type": "node",
                            "data": {
                                "nickname": "alice",
                                "user_id": "1001",
                                "content": [{"type": "text", "data": {"text": "上线前要确认"}}],
                            },
                        }
                    ]
                }
            )
        ),
    )

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [{"type": "chain", "chain": [Plain("转发总结失败：未配置消息解析模型。")]}]
    assert event.chain_calls == [[Plain("转发总结失败：未配置消息解析模型。")]]
    assert event.stopped == 1
    assert any(
        "stage=forward_summary_completed" in message
        and "message_id=msg-forward-private" in message
        and "provider_id=<none>" in message
        and "llm_success=false" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=chunk_replayed" in message
        and "message_id=msg-forward-private" in message
        and "chunk_source=forward_summary" in message
        and "chunk_summary_length=17" in message
        and "chunk_summary=" not in message
        for message in log_recorder.info
    )
    assert any(
        "stage=message_completed" in message
        and "message_id=msg-forward-private" in message
        and "chunk_count=1" in message
        for message in log_recorder.info
    )


def test_on_message_replays_forward_failure_text_when_transcript_is_empty(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], warning=[], exception=[])
    shared_logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
        exception=lambda message: log_recorder.exception.append(message),
    )
    monkeypatch.setattr(main, "logger", shared_logger)

    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    _patch_runtime_loggers(plugin, monkeypatch, shared_logger)
    event = FakeEvent(
        [Forward(id="forward-empty")],
        message_id="msg-forward-empty-main",
        onebot_client=types.SimpleNamespace(
            get_forward_msg=_make_async_raise(RuntimeError("boom"))
        ),
    )

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [
        {"type": "chain", "chain": [Plain("Merged forward parsing failed: no readable content.")]}
    ]
    assert event.chain_calls == [[Plain("Merged forward parsing failed: no readable content.")]]
    assert event.plain_calls == []
    assert event.stopped == 1
    assert any("stage=forward_summary_started" in message for message in log_recorder.info)
    assert any(
        "stage=forward_transcript_failed" in message
        and "error_type=ForwardTranscriptExtractionError" in message
        for message in log_recorder.warning
    )
    assert any(
        "stage=message_completed" in message
        and "message_id=msg-forward-empty-main" in message
        and "chunk_count=1" in message
        for message in log_recorder.info
    )
    assert log_recorder.exception == []


def test_on_message_private_success_path_replays_chunks_and_uses_private_origin(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], exception=[])
    monkeypatch.setattr(
        main,
        "logger",
        types.SimpleNamespace(
            info=lambda message: log_recorder.info.append(message),
            exception=lambda message: log_recorder.exception.append(message),
        ),
    )
    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    plugin._resolver = cast(
        OneBotMessageResolver,
        StubResolver(
            result=ResolvedMessage(
                log_summary=(
                    "plugin=chat_work_balance stage=message_resolved_summary "
                    "platform=aiocqhttp unified_msg_origin=aiocqhttp:private:1 "
                    "message_id=msg-private"
                ),
                replay_plan=ReplayPlan(
                    chunks=[
                        ReplayChunk(chain=[Plain("private first")], source_indexes=(0,), summary="private first"),
                        ReplayChunk(chain=[Plain("private second")], source_indexes=(1,), summary="private second"),
                    ]
                ),
            )
        ),
    )
    event = FakeEvent(
        [],
        message_id="msg-private",
        unified_msg_origin="aiocqhttp:private:1",
    )

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [
        {"type": "chain", "chain": [Plain("private first")]},
        {"type": "chain", "chain": [Plain("private second")]},
    ]
    assert event.chain_calls == [[Plain("private first")], [Plain("private second")]]
    assert event.stopped == 1
    assert any(
        "stage=message_received" in message
        and "message_id=msg-private" in message
        and "unified_msg_origin=aiocqhttp:private:1" in message
        for message in log_recorder.info
    )
    assert any(
        "stage=message_completed" in message
        and "message_id=msg-private" in message
        and "chunk_count=2" in message
        for message in log_recorder.info
    )
    assert log_recorder.exception == []


def test_on_message_stops_event_without_output_when_resolver_returns_empty_plan(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], exception=[])
    monkeypatch.setattr(
        main,
        "logger",
        types.SimpleNamespace(
            info=lambda message: log_recorder.info.append(message),
            exception=lambda message: log_recorder.exception.append(message),
        ),
    )
    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    plugin._resolver = cast(
        OneBotMessageResolver,
        StubResolver(
            result=ResolvedMessage(
                log_summary=(
                    "plugin=chat_work_balance stage=message_resolved_summary "
                    "platform=aiocqhttp unified_msg_origin=aiocqhttp:group:1 "
                    "message_id=msg-empty"
                ),
            )
        ),
    )
    event = FakeEvent([], message_id="msg-empty")

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == []
    assert event.chain_calls == []
    assert event.plain_calls == []
    assert event.stopped == 1
    assert any("stage=message_received" in message and "message_id=msg-empty" in message for message in log_recorder.info)
    assert any("stage=message_resolved_summary" in message and "message_id=msg-empty" in message for message in log_recorder.info)
    assert any(
        "stage=message_completed" in message
        and "message_id=msg-empty" in message
        and "chunk_count=0" in message
        for message in log_recorder.info
    )
    assert log_recorder.exception == []


def test_on_message_returns_short_error_when_resolver_raises(monkeypatch) -> None:
    log_recorder = types.SimpleNamespace(info=[], exception=[])
    monkeypatch.setattr(
        main,
        "logger",
        types.SimpleNamespace(
            info=lambda message: log_recorder.info.append(message),
            exception=lambda message: log_recorder.exception.append(message),
        ),
    )
    plugin = main.ChatWorkBalancePlugin(FakeContext(), {})
    plugin._resolver = cast(
        OneBotMessageResolver,
        StubResolver(error=RuntimeError("unexpected")),
    )
    event = FakeEvent([], message_id="msg-error")

    results = run_async(collect_async(plugin.on_message(event)))

    assert results == [
        {"type": "plain", "text": "Message resolver is temporarily unavailable."}
    ]
    assert event.plain_calls == ["Message resolver is temporarily unavailable."]
    assert event.stopped == 1
    assert any("stage=plugin_init" in message for message in log_recorder.info)
    assert any("stage=message_received" in message and "message_id=msg-error" in message for message in log_recorder.info)
    assert len(log_recorder.exception) == 1
    assert "stage=message_failed" in log_recorder.exception[0]
    assert "failure_stage=entry" in log_recorder.exception[0]
    assert "error_type=RuntimeError" in log_recorder.exception[0]
