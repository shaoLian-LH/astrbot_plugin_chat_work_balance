# 收紧平台安全 Replay Chunk 契约
## 目的
- 保证 `ReplayPlan.chunks` 不触发 QQ Official 单次发送吞组件行为。
- 保留完整解析顺序，同时让实际发送顺序服从平台安全边界。

## 前置任务依赖
- `01_enable_dual_qq_official_entry.md`

## 相关文件位置
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:39-247`
- `chat_work_balance/models.py:7-46`
- `chat_work_balance/services/merged_forward_reader.py:25-173`
- `tests/test_qq_channel_message_resolver.py:55-185`

## 可复用内容
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:49-61`：复用连续文本缓冲与 flush 机制。
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:80-118`：复用图片本体 chunk 与后续分析文本 chunk 的拆分方式。
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:120-174`：复用文件、语音、视频单独成 chunk 的处理方式。
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:176-210`：复用 `At`、`Face`、`Reply` dropped segment 记录方式。
- `chat_work_balance/services/merged_forward_reader.py:32-53`：复用 merged forward 摘要入口，继续转为文本回放。

## 如何执行
- 审查并补强 chunk 生成规则：文本可合并；图片、文件、语音、视频必须各自独立；图片分析结果只能进入后续文本 chunk。
- 确认 `Forward`、`Node`、`Nodes` 只生成摘要文本，不原样回放。
- 对 `At`、`Face`、`Reply` 等不稳定组件保持 dropped 或安全降级，并在 `segments` 与 `ReplayPlan.dropped_segments` 中可追踪。
- 补 resolver 测试，覆盖多富媒体、图片分析、forward 摘要、dropped segment 与 source index。

## 验收目标
- 每个 replay chunk 最多包含一种富媒体发送意图，不包含多个富媒体或不安全组件组合。
- 基础组件进入 `segments`，实际 `chunks` 与 QQ Official `_parse_to_qqofficial` 发送边界一致。
- `At`、`Face`、`Reply` 的处理结果可从 `segments` 与 `dropped_segments` 判断。

## 参考文件
- `.slfk/docs/plans/2026-05-13_17-34_replay-resolver-fix-design.md:42-61`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:619-692`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py:201-344`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md:7-19`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md:30-36`
