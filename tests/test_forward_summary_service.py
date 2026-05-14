from __future__ import annotations

# pyright: reportMissingImports=false

import types

from chat_work_balance.config import ChatWorkBalanceConfig
from chat_work_balance.services import forward_summary_service as service_module
from chat_work_balance.services.forward_summary_service import ForwardSummaryService
from tests.helpers import FakeContext, FakeProvider, run_async


def test_summarize_transcript_uses_message_provider_and_empty_image_urls() -> None:
    provider = FakeProvider(completion_text="张三：推进上线，保留“先灰度一天”。")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "global-message-provider",
                "default_image_caption_provider_id": "global-image-provider",
            }
        },
        providers={
            "message-provider": provider,
            "global-message-provider": FakeProvider(completion_text="unused"),
            "global-image-provider": FakeProvider(completion_text="unused"),
        },
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(
            image_analysis_provider_id="image-provider",
            message_resolve_provider_id="message-provider",
        ),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )
    transcript = "Alice(1001): 先灰度一天，再全量。"

    try:
        result = run_async(
            service.summarize_transcript(
                transcript,
                unified_msg_origin="aiocqhttp:group:1",
                source_label="forward:42#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is True
    assert result.provider_id == "message-provider"
    assert result.text == "张三：推进上线，保留“先灰度一天”。"
    assert "必须只用中文输出" in result.prompt
    assert "按发送者分组" in result.prompt
    assert "发送者 id" in result.prompt
    assert "发言维度" in result.prompt
    assert transcript in result.prompt
    assert provider.calls == [{"prompt": result.prompt, "image_urls": []}]
    assert log_recorder.warning == []
    assert len(log_recorder.info) == 1
    assert "stage=provider_succeeded" in log_recorder.info[0]
    assert "provider_id=message-provider" in log_recorder.info[0]
    assert "message_id=42" in log_recorder.info[0]
    assert transcript not in log_recorder.info[0]


def test_summarize_transcript_returns_failure_when_message_provider_missing() -> None:
    context = FakeContext(global_config={"provider_settings": {}}, providers={})
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.summarize_transcript(
                "Alice(1001): discuss launch plan",
                unified_msg_origin="umo",
                source_label="forward:43#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == ""
    assert result.text == "转发总结失败：未配置消息解析模型。"
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 1
    assert "stage=provider_configuration_error" in log_recorder.warning[0]
    assert "call_result=configuration_error" in log_recorder.warning[0]
    assert "provider_id=<none>" in log_recorder.warning[0]


def test_summarize_transcript_returns_failure_when_provider_not_found() -> None:
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "missing-provider",
            }
        },
        providers={},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.summarize_transcript(
                "Alice(1001): discuss launch plan",
                unified_msg_origin="umo",
                source_label="forward:44#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == "missing-provider"
    assert result.text == "转发总结失败：找不到消息解析模型 missing-provider。"
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 1
    assert "stage=provider_configuration_error" in log_recorder.warning[0]
    assert "provider_id=missing-provider" in log_recorder.warning[0]


def test_summarize_transcript_returns_failure_when_provider_type_is_invalid() -> None:
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "bad-provider",
            }
        },
        providers={"bad-provider": object()},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.summarize_transcript(
                "Alice(1001): discuss launch plan",
                unified_msg_origin="umo",
                source_label="forward:45#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == "bad-provider"
    assert result.text == "转发总结失败：消息解析模型 bad-provider 不是文本对话 provider。"
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 1
    assert "stage=provider_configuration_error" in log_recorder.warning[0]
    assert "provider_id=bad-provider" in log_recorder.warning[0]


def test_summarize_transcript_does_not_fallback_to_image_provider_id() -> None:
    image_provider = FakeProvider(completion_text="should not be used")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_image_caption_provider_id": "global-image-provider",
            }
        },
        providers={"image-provider": image_provider, "global-image-provider": FakeProvider()},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(image_analysis_provider_id="image-provider"),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.summarize_transcript(
                "Alice(1001): discuss launch plan",
                unified_msg_origin="umo",
                source_label="forward:46#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == ""
    assert result.text == "转发总结失败：未配置消息解析模型。"
    assert image_provider.calls == []
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 1


def test_summarize_transcript_does_not_fallback_to_default_provider_id() -> None:
    default_provider = FakeProvider(completion_text="should not be used")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_provider_id": "global-default-provider",
            }
        },
        providers={"global-default-provider": default_provider},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.summarize_transcript(
                "Alice(1001): discuss launch plan",
                unified_msg_origin="umo",
                source_label="forward:46a#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == ""
    assert result.text == "转发总结失败：未配置消息解析模型。"
    assert default_provider.calls == []
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 1
    assert "stage=provider_configuration_error" in log_recorder.warning[0]
    assert "provider_id=<none>" in log_recorder.warning[0]


def test_summarize_transcript_retries_three_times_on_provider_exception() -> None:
    provider = FakeProvider(outcomes=[RuntimeError("down-1"), RuntimeError("down-2"), RuntimeError("down-3")])
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "message-provider",
            }
        },
        providers={"message-provider": provider},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )
    transcript = "Alice(1001): launch today\nBob(1002): block by payment"

    try:
        result = run_async(
            service.summarize_transcript(
                transcript,
                unified_msg_origin="umo",
                source_label="forward:47#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == "message-provider"
    assert result.text == "转发总结失败：消息解析模型连续 3 次未返回有效摘要。"
    assert len(provider.calls) == 3
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 4
    assert "stage=provider_retry" in log_recorder.warning[0]
    assert "attempt=1" in log_recorder.warning[0]
    assert "error_type=RuntimeError" in log_recorder.warning[0]
    assert "attempt=2" in log_recorder.warning[1]
    assert "attempt=3" in log_recorder.warning[2]
    assert "stage=message_failed" in log_recorder.warning[3]
    assert transcript not in " ".join(log_recorder.warning)


def test_summarize_transcript_returns_failure_after_empty_text_retries() -> None:
    provider = FakeProvider(outcomes=["", "   ", ""])
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "message-provider",
            }
        },
        providers={"message-provider": provider},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.summarize_transcript(
                "Alice(1001): discuss launch plan",
                unified_msg_origin="umo",
                source_label="forward:48#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == "message-provider"
    assert result.text == "转发总结失败：消息解析模型连续 3 次未返回有效摘要。"
    assert len(provider.calls) == 3
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 4
    assert "call_result=empty_text" in log_recorder.warning[0]
    assert "call_result=empty_text" in log_recorder.warning[1]
    assert "call_result=empty_text" in log_recorder.warning[2]


def test_summarize_transcript_logs_do_not_expose_full_transcript() -> None:
    provider = FakeProvider(completion_text="李四：关键争议在排期，原话是“先清掉阻塞项”。")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_message_resolve_provider_id": "message-provider",
            }
        },
        providers={"message-provider": provider},
    )
    service = ForwardSummaryService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )
    transcript = "\n".join(
        [
            "Alice(1001): this line should never appear in logs",
            "Bob(1002): another sensitive line with customer details",
        ]
    )

    try:
        result = run_async(
            service.summarize_transcript(
                transcript,
                unified_msg_origin="umo",
                source_label="forward:49#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is True
    all_logs = " ".join(log_recorder.info + log_recorder.warning)
    assert "this line should never appear in logs" not in all_logs
    assert "another sensitive line with customer details" not in all_logs
