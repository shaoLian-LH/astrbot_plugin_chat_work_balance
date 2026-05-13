from __future__ import annotations

# pyright: reportMissingImports=false

import asyncio
import types

from astrbot.api.star import Context
from astrbot.core.provider.provider import Provider


class FakeProviderResponse:
    def __init__(self, completion_text: str) -> None:
        self.completion_text = completion_text


class FakeProvider(Provider):
    def __init__(
        self,
        *,
        completion_text: str = "A generated caption",
        error: Exception | None = None,
    ) -> None:
        self.completion_text = completion_text
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def text_chat(self, prompt: str, image_urls: list[str]) -> FakeProviderResponse:
        self.calls.append({"prompt": prompt, "image_urls": list(image_urls)})
        if self.error is not None:
            raise self.error
        return FakeProviderResponse(self.completion_text)


class FakeContext(Context):
    def __init__(
        self,
        *,
        global_config: dict[str, object] | None = None,
        providers: dict[str, object] | None = None,
    ) -> None:
        self._global_config = global_config or {}
        self._providers = providers or {}

    def get_config(self, unified_msg_origin: str) -> dict[str, object]:
        del unified_msg_origin
        return self._global_config

    def get_provider_by_id(self, provider_id: str) -> object | None:
        return self._providers.get(provider_id)


class FakeEvent:
    def __init__(
        self,
        message: list[object],
        *,
        message_id: str = "msg-1",
        unified_msg_origin: str = "aiocqhttp:group:1",
    ) -> None:
        self.message_obj = types.SimpleNamespace(message=message, message_id=message_id)
        self.unified_msg_origin = unified_msg_origin
        self.chain_calls: list[list[object]] = []
        self.plain_calls: list[str] = []
        self.stopped = 0

    def chain_result(self, chain: list[object]) -> dict[str, object]:
        materialized = list(chain)
        self.chain_calls.append(materialized)
        return {"type": "chain", "chain": materialized}

    def plain_result(self, text: str) -> dict[str, str]:
        self.plain_calls.append(text)
        return {"type": "plain", "text": text}

    def stop_event(self) -> None:
        self.stopped += 1


async def collect_async(async_iterable) -> list[object]:
    results: list[object] = []
    async for item in async_iterable:
        results.append(item)
    return results


def run_async(awaitable):
    return asyncio.run(awaitable)
