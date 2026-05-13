## Scope

- 目标只收缩到“replay resolver 修复计划应包含什么”，不重开插件骨架、provider 选型、合并转发整体设计。
- 事实边界只来自当前仓库、`.slfk/docs/finished/*`、`.slfk/tmp/astrbot-src` 中与 `qqofficial` / `qqofficial_webhook` / message components / event filter 直接相关的文件。
- 当前仓库已经不是空模板状态：`main.py` 已监听 `QQOFFICIAL` 全消息并逐 chunk 回放，`metadata.yaml` 已声明 `qq_official`，resolver / config / services / tests 已存在。见 `main.py:15-47`、`metadata.yaml:1-8`、`chat_work_balance/config.py:11-61`、`chat_work_balance/models.py:7-46`。

## Findings

- 最小必要修复的根因在 QQ Official 发送器，不在“能否读完整消息链”。
  - resolver 已从 `event.message_obj.message` 读取完整组件，并把文本、图片、文件、语音、视频、转发摘要拆成多个 `ReplayChunk`。见 `chat_work_balance/resolvers/qq_channel_message_resolver.py:39-279`。
  - 真实发送端 `_parse_to_qqofficial` 仍只保留第一张图、第一段语音、第一段视频、第一份文件，其余组件走 `logger.debug(f"qq_official 忽略 {i.type}")`。见 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:620-684`。
  - `send_by_session` 和事件回包最终都复用这一套解析语义，所以问题是平台发送语义收窄，不是 resolver 没拆 chunk。见 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:202-225`、`.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py:201-344`。

- 当前仓库里“修 replay resolver”所需的大部分基础设施已经落地，不应再次纳入新计划。
  - 平台过滤、事件消费、异常兜底已经在入口完成。见 `main.py:35-47`。
  - provider 配置优先级和全局 prompt 读取已经在 `ChatWorkBalanceConfig` 中完成。见 `chat_work_balance/config.py:11-61`。
  - 图片分析 provider 选择、归一化、失败降级已经在 `ResourceAnalysisService` 中完成。见 `chat_work_balance/services/resource_analysis_service.py:31-159`。
  - 合并转发三层截断、节点上限、嵌套图片摘要已经在 `MergedForwardReader` 中完成。见 `chat_work_balance/services/merged_forward_reader.py:25-173`。
  - 这些行为已有针对性测试。见 `tests/test_main.py:67-123`、`tests/test_qq_channel_message_resolver.py:55-185`、`tests/test_merged_forward_reader.py:39-110`。

- 让原 plan 变大的，不是 replay 修复本身，而是把“插件建设”和“平台限制应对”混在了一起。
  - finished design 把模块目录、`_conf_schema.json`、provider 接入、合并转发读取、日志模型、验证矩阵一起打包，范围已经是完整插件方案。见 `.slfk/docs/finished/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:23-131`。
  - finished task 也按 `initialize skeleton` / `implement resolver and services` / `tests and verification` 三个 slice 编排，说明当时执行对象是“从模板到可用插件”，不是一次 replay bugfix。见 `.slfk/docs/finished/tasks/2026-05-12_20-07_qq-channel-message-resolver/PLAN.md:3-43`、`.slfk/docs/finished/tasks/2026-05-12_20-07_qq-channel-message-resolver/01_initialize_plugin_skeleton.md:27-39`、`.slfk/docs/finished/tasks/2026-05-12_20-07_qq-channel-message-resolver/02_implement_resolver_and_services.md:24-40`。

- `qqofficial` 和 `qqofficial_webhook` 在过滤层是两个独立平台类型，修复计划如果不明确目标平台，范围会被动扩大。
  - 过滤枚举同时存在 `QQOFFICIAL` 和 `QQOFFICIAL_WEBHOOK`，adapter key 也不同。见 `.slfk/tmp/astrbot-src/astrbot/core/star/filter/platform_adapter_type.py:9-54`。
  - 当前插件只监听 `QQOFFICIAL`，不是 `QQOFFICIAL_WEBHOOK`。见 `main.py:35-36`。
  - webhook event 只是继承 `QQOfficialMessageEvent`，但是否纳入修复仍是设计范围选择，不是当前实现必然包含。见 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_event.py:1-17`。

- 现有测试已证明“resolver 内部顺序”基本成立，但还没有证明“真实 QQOfficial 适配器收到这些 chunk 后完全符合回放预期”。
  - resolver 测试验证了 `Plain -> Image -> analysis -> File` 顺序、富媒体拆 chunk、forward 摘要插入。见 `tests/test_qq_channel_message_resolver.py:72-185`。
  - 这些测试使用的是 `FakeEvent` / stub service，不覆盖 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:620-684` 的真实丢组件行为。

- 最小必要修复应优先聚焦“回放 chunk 约束是否要再收紧”，而不是继续扩充 resolver 能力。
  - resolver 现在会把 `At` / `Face` / `Reply` 标成 dropped，把 `Forward` / `Node` / `Nodes` 收敛成文本摘要，这已经是在适配 QQOfficial 发送限制。见 `chat_work_balance/resolvers/qq_channel_message_resolver.py:176-243`。
  - 真正仍有不确定性的地方，是单个 chunk 是否可能含“文本 + 一个富媒体”，以及 channel / group / friend 三种 scene 下可发送语义是否一致。证据见 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py:238-344`。

## Options

- 最小修复范围。
  - 只讨论并验证 `ReplayChunk` 对 QQ Official 的发送约束。
  - 明确每个 chunk 允许的组件组合，直接以 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:620-684` 为硬边界。
  - 不重新设计 resolver/provider/forward reader；只在必要时调整 chunk 生成规则或补一层“platform-safe chunk normalizer”。

- 中等范围。
  - 在最小修复范围基础上，再补 `QQOFFICIAL_WEBHOOK` 是否共用同一修复。
  - 前提是设计文档明确：当前只做枚举和事件链路影响分析，不承诺同时改两套入口。

- 膨胀范围，当前不建议。
  - 重新讨论 `_conf_schema.json`、provider prompt、转发摘要深度、日志字段、完整测试矩阵。
  - 这些内容在仓库里已基本实现，重新纳入只会把“修 replay”变回“重做设计”。

- 如果要落成一个小设计文档，建议只分 4 节。
  - `Problem Statement`：真实 QQ Official 发送器会吞哪些组件，当前 resolver 已做了什么。
  - `Non-Goals`：不重做 provider、forward reader、plugin skeleton；默认不扩到 webhook。
  - `Replay Chunk Contract`：每种组件如何映射到 platform-safe chunk，哪些组件只能转摘要或 dropped。
  - `Verification`：用真实 `_parse_to_qqofficial` 语义做验证，而不是只看 FakeEvent。

## Risks

- 如果修复计划继续把 provider / forward / skeleton 带进去，讨论焦点会从“平台发送边界”偏成“插件整体能力”，很难收口。
- 如果不先明确 `QQOFFICIAL` 还是 `QQOFFICIAL + QQOFFICIAL_WEBHOOK`，过滤枚举和 event class 会把设计面自然扩成双平台。见 `.slfk/tmp/astrbot-src/astrbot/core/star/filter/platform_adapter_type.py:9-54`、`.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_event.py:1-17`。
- 如果只看 resolver 单测，不看真实 `_parse_to_qqofficial`，会误判“拆 chunk 已经足够”，但平台层仍可能吞掉同 chunk 中的后续富媒体。见 `tests/test_qq_channel_message_resolver.py:72-185` 对比 `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:620-684`。
- 当前入口对成功和失败都会 `event.stop_event()`；如果后续把修复目标改成“只增强 replay，不拦截默认聊天”，设计边界会再次扩大。见 `main.py:41-47`。

## References

- `main.py:15-47`
- `metadata.yaml:1-8`
- `chat_work_balance/config.py:11-61`
- `chat_work_balance/models.py:7-46`
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:39-337`
- `chat_work_balance/services/resource_analysis_service.py:31-159`
- `chat_work_balance/services/merged_forward_reader.py:25-173`
- `tests/test_main.py:67-123`
- `tests/test_qq_channel_message_resolver.py:55-185`
- `tests/test_merged_forward_reader.py:39-110`
- `.slfk/docs/finished/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:23-131`
- `.slfk/docs/finished/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md:7-26`
- `.slfk/docs/finished/tasks/2026-05-12_20-07_qq-channel-message-resolver/PLAN.md:3-43`
- `.slfk/docs/finished/tasks/2026-05-12_20-07_qq-channel-message-resolver/01_initialize_plugin_skeleton.md:27-39`
- `.slfk/docs/finished/tasks/2026-05-12_20-07_qq-channel-message-resolver/02_implement_resolver_and_services.md:24-40`
- `.slfk/tmp/astrbot-src/astrbot/core/star/filter/platform_adapter_type.py:9-74`
- `.slfk/tmp/astrbot-src/astrbot/core/star/filter/event_message_type.py:10-33`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/astr_message_event.py:103-182`
- `.slfk/tmp/astrbot-src/astrbot/core/message/components.py:42-66`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:202-225`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:620-684`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py:201-344`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_event.py:1-17`
