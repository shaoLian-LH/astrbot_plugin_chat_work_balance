from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false

import sys
import types
from dataclasses import dataclass, field


def _install_astrbot_stubs() -> None:
    if "astrbot" in sys.modules:
        return

    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    star_module = types.ModuleType("astrbot.api.star")
    core_module = types.ModuleType("astrbot.core")
    message_module = types.ModuleType("astrbot.core.message")
    components_module = types.ModuleType("astrbot.core.message.components")
    provider_package = types.ModuleType("astrbot.core.provider")
    provider_module = types.ModuleType("astrbot.core.provider.provider")

    class AstrBotConfig(dict):
        pass

    class _Logger:
        def info(self, *args, **kwargs) -> None:
            return None

        def warning(self, *args, **kwargs) -> None:
            return None

        def exception(self, *args, **kwargs) -> None:
            return None

    class PlatformAdapterType:
        AIOCQHTTP = "aiocqhttp"

    class EventMessageType:
        ALL = "all"

    def _decorator(*_args, **_kwargs):
        def _wrap(func):
            return func

        return _wrap

    class _FilterNamespace:
        @staticmethod
        def platform_adapter_type(*_args, **_kwargs):
            return _decorator(*_args, **_kwargs)

        @staticmethod
        def event_message_type(*_args, **_kwargs):
            return _decorator(*_args, **_kwargs)

    class AstrMessageEvent:
        pass

    class Context:
        pass

    class Star:
        def __init__(self, context: Context | None = None) -> None:
            self.context = context

    def register(*_args, **_kwargs):
        return _decorator(*_args, **_kwargs)

    @dataclass
    class BaseMessageComponent:
        pass

    @dataclass
    class Plain(BaseMessageComponent):
        text: str = ""

    @dataclass
    class Image(BaseMessageComponent):
        file: str
        url: str = ""
        file_path: str = "/tmp/image.png"
        base64_data: str = "ZmFrZS1pbWFnZQ=="
        file_path_error: Exception | None = None
        base64_error: Exception | None = None

        async def convert_to_file_path(self) -> str:
            if self.file_path_error is not None:
                raise self.file_path_error
            return self.file_path

        async def convert_to_base64(self) -> str:
            if self.base64_error is not None:
                raise self.base64_error
            return self.base64_data

    @dataclass
    class File(BaseMessageComponent):
        name: str = ""
        url: str = ""
        file: str = ""
        get_file_result: str | None = None
        get_file_error: Exception | None = None

        async def get_file(self, allow_return_url: bool = True) -> str | None:
            del allow_return_url
            if self.get_file_error is not None:
                raise self.get_file_error
            if self.get_file_result is not None:
                return self.get_file_result
            if self.url:
                return self.url
            if self.file:
                return self.file
            return None

    @dataclass
    class Record(BaseMessageComponent):
        file: str = ""

    @dataclass
    class Video(BaseMessageComponent):
        file: str = ""

    @dataclass
    class At(BaseMessageComponent):
        qq: str = ""

    @dataclass
    class Face(BaseMessageComponent):
        id: str = ""

    @dataclass
    class Reply(BaseMessageComponent):
        id: str = ""

    @dataclass
    class Forward(BaseMessageComponent):
        id: str = ""

    @dataclass
    class Node(BaseMessageComponent):
        name: str = ""
        uin: str = ""
        content: list[BaseMessageComponent] = field(default_factory=list)

    @dataclass
    class Nodes(BaseMessageComponent):
        nodes: list[Node] = field(default_factory=list)

    class Provider:
        async def text_chat(self, prompt: str, image_urls: list[str]):
            raise NotImplementedError

    api_module.AstrBotConfig = AstrBotConfig
    api_module.logger = _Logger()
    api_module.event = event_module
    api_module.star = star_module

    _FilterNamespace.PlatformAdapterType = PlatformAdapterType
    _FilterNamespace.EventMessageType = EventMessageType

    event_module.AstrMessageEvent = AstrMessageEvent
    event_module.filter = _FilterNamespace()

    star_module.Context = Context
    star_module.Star = Star
    star_module.register = register

    provider_module.Provider = Provider

    for component_cls in [
        At,
        BaseMessageComponent,
        Face,
        File,
        Forward,
        Image,
        Node,
        Nodes,
        Plain,
        Record,
        Reply,
        Video,
    ]:
        setattr(components_module, component_cls.__name__, component_cls)

    astrbot_module.api = api_module
    astrbot_module.core = core_module
    core_module.message = message_module
    core_module.provider = provider_package
    message_module.components = components_module
    provider_package.provider = provider_module

    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module
    sys.modules["astrbot.core"] = core_module
    sys.modules["astrbot.core.message"] = message_module
    sys.modules["astrbot.core.message.components"] = components_module
    sys.modules["astrbot.core.provider"] = provider_package
    sys.modules["astrbot.core.provider.provider"] = provider_module


_install_astrbot_stubs()
