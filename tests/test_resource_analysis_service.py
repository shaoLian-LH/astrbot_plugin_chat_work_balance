from __future__ import annotations

# pyright: reportMissingImports=false

import types

from astrbot.core.message.components import Image

from chat_work_balance.config import ChatWorkBalanceConfig
from chat_work_balance.services import resource_analysis_service as service_module
from chat_work_balance.services.resource_analysis_service import ResourceAnalysisService
from tests.helpers import FakeContext, FakeProvider, run_async


def test_analyze_image_prefers_plugin_provider_over_global_default() -> None:
    provider = FakeProvider(completion_text="Desk photo")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_image_caption_provider_id": "global-provider",
                "image_caption_prompt": "Summarize the image",
            }
        },
        providers={"plugin-provider": provider, "global-provider": FakeProvider()},
    )
    service = ResourceAnalysisService(
        context=context,
        plugin_config=ChatWorkBalanceConfig(image_analysis_provider_id="plugin-provider"),
    )
    log_recorder = types.SimpleNamespace(info=[], warning=[])
    original_logger = service_module.logger
    service_module.logger = types.SimpleNamespace(
        info=lambda message: log_recorder.info.append(message),
        warning=lambda message: log_recorder.warning.append(message),
    )

    try:
        result = run_async(
            service.analyze_image(
                Image(file_path="/tmp/plugin.png"),
                unified_msg_origin="umo",
                source_label="message:1#0",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is True
    assert result.provider_id == "plugin-provider"
    assert result.prompt == "Summarize the image"
    assert result.text == "Image analysis: Desk photo"
    assert provider.calls == [
        {"prompt": "Summarize the image", "image_urls": ["file:///tmp/plugin.png"]}
    ]
    assert log_recorder.warning == []
    assert len(log_recorder.info) == 1
    assert "stage=provider_succeeded" in log_recorder.info[0]
    assert "provider_id=plugin-provider" in log_recorder.info[0]
    assert "message_id=1" in log_recorder.info[0]


def test_analyze_image_uses_global_default_and_base64_fallback() -> None:
    provider = FakeProvider(completion_text="Team chart")
    context = FakeContext(
        global_config={
            "provider_settings": {
                "default_image_caption_provider_id": "global-provider",
                "image_caption_prompt": "Explain this chart",
            }
        },
        providers={"global-provider": provider},
    )
    service = ResourceAnalysisService(
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
            service.analyze_image(
                Image(
                    file_path_error=RuntimeError("no file path"),
                    base64_data="YmFzZTY0LWltYWdl",
                ),
                unified_msg_origin="umo",
                source_label="message:1#1",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is True
    assert result.provider_id == "global-provider"
    assert result.text == "Image analysis: Team chart"
    assert provider.calls == [
        {
            "prompt": "Explain this chart",
            "image_urls": ["base64://YmFzZTY0LWltYWdl"],
        }
    ]
    assert log_recorder.warning == []
    assert len(log_recorder.info) == 1
    assert "stage=provider_succeeded" in log_recorder.info[0]
    assert "provider_id=global-provider" in log_recorder.info[0]


def test_analyze_image_returns_failure_when_provider_call_raises() -> None:
    provider = FakeProvider(error=RuntimeError("provider down"))
    context = FakeContext(
        global_config={
            "provider_settings": {"default_image_caption_provider_id": "global-provider"}
        },
        providers={"global-provider": provider},
    )
    service = ResourceAnalysisService(
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
            service.analyze_image(
                Image(file_path="/tmp/failure.png"),
                unified_msg_origin="umo",
                source_label="message:1#2",
            )
        )
    finally:
        service_module.logger = original_logger

    assert result.success is False
    assert result.provider_id == "global-provider"
    assert result.detail == "Image analysis failed during provider call."
    assert result.text == "Image analysis failed during provider call."
    assert log_recorder.info == []
    assert len(log_recorder.warning) == 1
    assert "stage=message_failed" in log_recorder.warning[0]
    assert "failure_stage=provider_call" in log_recorder.warning[0]
    assert "provider_id=global-provider" in log_recorder.warning[0]
