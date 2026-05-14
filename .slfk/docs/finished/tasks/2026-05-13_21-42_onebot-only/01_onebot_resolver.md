# OneBot Resolver 语义收敛
## 目的
- 删除 QQ Official 专属 resolver 语义，保留当前可复用解析能力。
- 让仓库只暴露 OneBot resolver，并保持 `ReplayPlan` / `ReplayChunk` / `ResolvedMessage` 模型不变。

## 前置任务依赖
- 无

## 相关文件位置
- chat_work_balance/resolvers/qq_channel_message_resolver.py:31-450
- chat_work_balance/resolvers/__init__.py:6-23
- chat_work_balance/models.py:7-47
- chat_work_balance/services/resource_analysis_service.py:33-212
- chat_work_balance/services/merged_forward_reader.py:32-173

## 可复用内容
- chat_work_balance/resolvers/qq_channel_message_resolver.py:42-310 复用消息链到 `ResolvedMessage` / `ReplayPlan` 的主体解析流程。
- chat_work_balance/resolvers/qq_channel_message_resolver.py:312-337 复用文件组件转可回放 `File` 的逻辑。
- chat_work_balance/resolvers/qq_channel_message_resolver.py:339-383 复用 resolver 摘要日志结构，但移除 QQ Official 命名。
- chat_work_balance/models.py:7-47 复用内部 replay 数据模型。
- chat_work_balance/services/merged_forward_reader.py:32-173 复用合并转发摘要能力。
- chat_work_balance/services/resource_analysis_service.py:33-129 复用图片分析能力与失败返回结构。

## 如何执行
- 将 `qq_channel_message_resolver.py` 替换为 OneBot resolver 文件，例如 `onebot_message_resolver.py`。
- 将类名、docstring、导出名改为 OneBot 语义，移除 `QQChannelMessageResolver` 对外暴露。
- 保持文本、图片、文件、语音、视频、合并转发的 chunk 规划规则。
- 保持 `At` / `Face` / `Reply` dropped 行为；其他无法可靠回放的未知组件要显式形成 dropped 记录，不静默吞掉。
- 将 resolver 内 source label 和日志字段改成 OneBot 可解释格式，不再依赖 `qq_official:channel:1`。

## 验收目标
- 仓库运行时代码不再导入或导出 `QQChannelMessageResolver`。
- 当前 resolver 目录只保留 OneBot resolver 实现。
- `ReplayPlan` / `ReplayChunk` / `ResolvedMessage` 模型仍由 resolver 返回并可被入口回放。
- resolver 相关日志和 source label 不再出现 `qq_official`、`QQOfficial`、`QQChannel`。

## 参考文件
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:3-14
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:24-41
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:53-66
- .slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/01-codebase-hooks.md:13-20
- .slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/02-docs-event-surface.md:20-33
