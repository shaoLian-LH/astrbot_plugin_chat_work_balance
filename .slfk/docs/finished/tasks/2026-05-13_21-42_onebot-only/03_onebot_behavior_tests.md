# OneBot 行为测试证据
## 目的
- 用可运行 UT 证明 OneBot 私聊和群聊行为成立。
- 删除旧的 QQ Official 声明型断言，测试焦点转为解析、回放、停止事件。

## 前置任务依赖
- 01_onebot_resolver.md
- 02_entrypoint_metadata_docs.md

## 相关文件位置
- tests/conftest.py:37-41
- tests/helpers.py:53-77
- tests/test_main.py:27-313
- tests/test_qq_channel_message_resolver.py:10-320
- pyproject.toml:7-10

## 可复用内容
- tests/helpers.py:53-77 复用 `FakeEvent`，扩展默认 `unified_msg_origin` 和会话类型上下文以覆盖 OneBot 私聊/群聊。
- tests/helpers.py:80-88 复用 async 收集和运行工具。
- tests/test_main.py:60-72 复用 `StubResolver` 模拟成功、空输出和异常路径。
- tests/test_main.py:145-190 复用按顺序回放 chunk 并停止事件的断言结构。
- tests/test_main.py:193-281 复用真实 resolver + 图片分析的端到端入口日志断言。
- tests/test_main.py:284-313 复用 resolver 异常时短错误消息和停止事件断言。
- tests/test_qq_channel_message_resolver.py:56-67 复用 resolver 构造 helper，改为 OneBot resolver。
- tests/test_qq_channel_message_resolver.py:70-320 复用文本、图片、富媒体、转发、dropped、失败继续回放的组件覆盖用例。

## 如何执行
- 将 AstrBot stub 的平台枚举改成 OneBot / aiocqhttp，并删除测试里动态补 `QQOFFICIAL_WEBHOOK` 的逻辑。
- 将入口注册测试改为验证只监听 OneBot / aiocqhttp，且不再证明双 QQ 平台。
- 增加 OneBot 私聊成功路径和群聊成功路径；两者断言主流程一致，只允许日志上下文不同。
- 增加空输出路径测试，断言无 `chain_result` / `plain_result`，但会记录完成态并 `stop_event()`。
- 将 resolver 测试文件和导入改为 OneBot 命名，所有 `qq_official:channel:1` 断言改成稳定 OneBot 来源格式。
- 执行 `rtk proxy uv run --group dev --python 3.10 python -m pytest` 和针对改动文件的 `rtk pyright ...`，修复失败。

## 验收目标
- 测试不再出现 `QQOFFICIAL`、`QQOFFICIAL_WEBHOOK`、`qq_official:channel:1`、`QQChannelMessageResolver`。
- UT 覆盖 OneBot 私聊、群聊、空输出、异常路径、组件解析、source label / log summary。
- `rtk proxy uv run --group dev --python 3.10 python -m pytest` 通过。
- 针对改动 Python 文件的 `rtk pyright` 通过。

## 参考文件
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:76-90
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:53-66
- .slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/01-codebase-hooks.md:18-21
- .slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/02-docs-event-surface.md:20-33
- https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html
