# Resolver 集成与验证
## 目的
- 在 resolver 中串联“抽取 transcript -> LLM 总结 -> 回放文本”。
- 保持群聊、私聊通过当前事件 `chain_result()` 回发的路径不变。
- 用集成测试覆盖成功、失败和日志字段。

## 前置任务依赖
- `01_extract_forward_transcript.md`
- `02_forward_summary_service.md`

## 相关文件位置
- `main.py:24-35`
- `main.py:47-102`
- `chat_work_balance/resolvers/onebot_message_resolver.py:34-40`
- `chat_work_balance/resolvers/onebot_message_resolver.py:260-277`
- `chat_work_balance/resolvers/onebot_message_resolver.py:297-314`
- `chat_work_balance/resolvers/onebot_message_resolver.py:343-387`
- `chat_work_balance/models.py:7-47`
- `tests/test_onebot_message_resolver.py:35-43`
- `tests/test_onebot_message_resolver.py:201-237`
- `tests/test_main.py:138-406`
- `tests/helpers.py:53-78`

## 可复用内容
- `chat_work_balance/resolvers/onebot_message_resolver.py:260-277`：复用 `forward_summary` segment 和 text chunk 回放形态。
- `main.py:62-102`：复用成功回放、异常回退和 `stop_event()` 路径。
- `chat_work_balance/models.py:7-47`：复用 `ResolvedSegment.metadata`、`ReplayChunk` 和 `ReplayPlan` 数据结构。
- `tests/test_onebot_message_resolver.py:201-237`：复用转发组件只产出总结文本的集成断言。
- `tests/test_main.py:138-406`：复用群聊、私聊、空结果、异常路径测试形态。

## 如何执行
- 在 `main.py` 初始化 `ForwardSummaryService`，并把 `plugin_config` 注入 `MergedForwardReader` 或其配置参数。
- 更新 `OneBotMessageResolver` 构造函数，接收 `ForwardSummaryService`；遇到 `Forward/Node/Nodes` 时先 `extract()`，再 `summarize()`。
- 抽取异常直接向上抛出，让 `main.py` 进入现有错误路径并 `stop_event()`；总结服务返回的失败摘要仍按普通 `forward_summary` 回放。
- 日志补齐转发入口、展开数量、过滤数量、每层采样、有效 transcript 数、provider id、LLM 成败、摘要字符数；不输出完整转发正文。
- 更新 `tests/test_onebot_message_resolver.py` 和 `tests/test_main.py`，覆盖 `forward_summary` segment、text chunk、群聊/私聊回发、无有效内容异常、日志字段。

## 验收目标
- resolver 输出仍包含 `forward_summary` segment，最终 text `ReplayChunk` 内容为 LLM 摘要或明确失败摘要。
- 群聊和私聊继续通过当前事件回发，不新增主动发送路径。
- 无有效转发内容时不调用 LLM，`main.py` 返回现有短错误并停止事件。
- 以下命令通过：
```bash
rtk proxy uv run --group dev --python 3.10 python -m pytest tests/test_merged_forward_reader.py tests/test_forward_summary_service.py tests/test_onebot_message_resolver.py tests/test_main.py
rtk pyright chat_work_balance/services/merged_forward_reader.py chat_work_balance/services/forward_summary_service.py chat_work_balance/resolvers/onebot_message_resolver.py main.py
```

## 参考文件
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:61-121`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md:15-50`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/02-official-docs.md:44-53`
- `https://docs.astrbot.app/dev/star/guides/send-message.html`
