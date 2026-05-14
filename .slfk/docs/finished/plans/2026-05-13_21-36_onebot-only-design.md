# OneBot Only Design

## Section 1: 范围与架构

插件对外只支持 `aiocqhttp / OneBot`，覆盖群聊和私聊。`qq_official` / `qq_official_webhook` 的平台声明、入口过滤、日志文案、专属 resolver、以及对应 UT 全部移除，不保留假支持。

内部仍保留“统一入口 + resolver 层”的架构，但语义要纠正：

- `main.py` 保留单一 `on_message(AstrMessageEvent)` 入口，只注册 OneBot 平台。
- 入口层只做事件接收、日志、异常边界、chunk 回放、`event.stop_event()`。
- resolver 层保留为可扩展结构，但当前仓库里只存在 OneBot resolver。也就是说，保留“未来可扩平台”的形状，不保留“今天无法验证的平台代码”。
- `ReplayPlan`、`ReplayChunk`、资源分析、合并转发摘要这类平台弱相关能力继续复用，但所有平台名、来源格式、日志字段里的 QQ Official 假设都要改成通用或 OneBot 语义。

这样做的边界很清楚：架构为未来留口，资产只为今天可验证的平台负责，不再出现“代码看起来支持，实际上没人能测”的状态。

### References

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/metadata.yaml`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/01-codebase-hooks.md`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/02-docs-event-surface.md`
- https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html

## Section 2: 删除与保留清单

删除范围要一次做干净，不保留“未来也许有用”的 QQ Official 资产：

- 删除 `metadata.yaml` 中 `qq_official`、`qq_official_webhook` 支持声明，改成只声明 OneBot 对应平台。
- 删除 `main.py` 里针对 `QQOFFICIAL` / `QQOFFICIAL_WEBHOOK` 的平台过滤、启动日志文案、以及任何写死为 QQ Official 的平台名输出。
- 删除 `chat_work_balance/resolvers/qq_channel_message_resolver.py`，并移除对它的直接依赖。
- 删除所有以 QQ Official 为前提写的测试断言，包括平台枚举 stub、双平台装饰器 AST 断言、`qq_official:channel:1` 这类来源字符串断言、以及“metadata 声明双 QQ 平台”的测试。
- 删除 README、CHANGELOG、`metadata.yaml` 描述里对 QQ Official skeleton 的定位，避免文档继续误导。

保留范围不是“原封不动保留”，而是“抽掉平台假设后继续复用”：

- 保留 `ReplayPlan` / `ReplayChunk` / `ResolvedMessage` 这套内部模型。
- 保留资源分析、合并转发摘要等平台弱相关服务，但把它们的日志和 source label 规则改成 OneBot 可解释的命名。
- 保留 resolver 分层目录结构，但当前只留下 OneBot resolver，例如改成 `onebot_message_resolver.py`，或者用一个更中性的抽象名再由主入口只实例化 OneBot 版本。
- 保留入口层的 replay 主流程，因为这部分和平台关系最弱，真正要替换的是它调用的 resolver 和平台过滤。

明确原则：凡是测试里无法在本地或 CI 构造出可靠 OneBot 证据的旧 QQ 资产，直接删，不迁就。

### References

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/metadata.yaml`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/README.md`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/CHANGELOG.md`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/resolvers/qq_channel_message_resolver.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/test_main.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/01-codebase-hooks.md`

## Section 3: OneBot 消息流与私聊/群聊行为规则

插件只监听 OneBot 的 `AstrMessageEvent` 消息事件，群聊和私聊统一进入同一个 `on_message`。入口收到事件后，先提取最小必要上下文：`message_id`、`unified_msg_origin`、消息链、会话类型标识。这里不要求入口自己理解群私聊差异，只要把事件原样交给 OneBot resolver。

OneBot resolver 的职责是把 AstrBot 已标准化的消息链翻译成内部 `ReplayPlan`。对群聊和私聊，核心解析规则应一致：文本直接保留，图片/文件/语音/视频/合并转发按组件能力转成可回放 chunk 或摘要；不支持的组件显式记录 dropped segment，而不是静默吞掉。也就是说，群聊和私聊的差异主要体现在日志标签和可能的后续策略扩展，不应该体现在两套不同解析流程。

事件结束规则也要定死：

- resolver 成功产出一个或多个 chunk，就按顺序 `yield event.chain_result(...)` 回放，回放结束后 `event.stop_event()`。
- resolver 成功但没有可回放 chunk，也要记录“已处理但无输出”的完成日志，然后 `event.stop_event()`，避免消息继续落回 AstrBot 默认回复链造成双响应。
- resolver 抛异常时，记录失败日志，返回一条短错误消息，再 `event.stop_event()`。
- 只有在明确判定“这不是插件应处理的消息类型”时，才允许不 stop；但按当前目标，群聊和私聊都处理，所以正常设计里这个分支应极少，甚至可以不暴露出来。

核心原则：私聊和群聊不是两条产品线，而是同一 OneBot 插件能力落在两种会话上下文里。这样测试也更直接，不会变成“群聊一套逻辑，私聊另一套补丁”。

### References

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/resolvers/qq_channel_message_resolver.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/helpers.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/02-docs-event-surface.md`
- https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html

## Section 4: 测试与验证设计

测试要从“证明声明存在”改成“证明 OneBot 行为成立”。不再保留 AST 级别的双 QQ 平台装饰器断言，不再保留 `metadata` 双平台声明测试；新的测试重点应该是 OneBot 私聊和群聊进入统一入口后，插件是否真的解析、回放、停止事件。

最小必须锁住的 UT：

- 入口注册测试：验证 `main.py` 只声明 OneBot 平台监听，而不是 QQ Official。
- 私聊成功路径：构造 OneBot 私聊事件，断言会进入 resolver、按顺序回放 chunk、最终 `stop_event()`，且不会落回默认 AstrBot 回复。
- 群聊成功路径：构造 OneBot 群聊事件，断言行为和私聊一致，只允许日志上下文不同，不允许主流程不同。
- 空输出路径：resolver 成功但 `ReplayPlan.chunks` 为空时，不应双回复；应记录完成态并 `stop_event()`。
- 异常路径：resolver 抛异常时，应产出短错误消息并停止事件。
- resolver 组件覆盖测试：基于 OneBot 在 AstrBot 中暴露出来的标准消息组件，重新确认文本、图片、文件、语音、视频、合并转发、不支持组件的 dropped 行为。
- source label / log summary 测试：删除 `qq_official:channel:1` 这类断言，改成只验证 OneBot 可解释、可稳定构造的来源格式。

验证策略也要改：不再把“存在一个 resolver 文件”和“metadata 里写了平台名”当成支持证据。支持证据只能来自可运行的 UT，最好每条关键路径都能在 fake event 下稳定复现。对于当前还不确定的 OneBot 事件细节，比如某些 notice/request 是否进入同一消息面，不纳入首版承诺，避免测试写成猜测。

### References

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/test_main.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/test_qq_channel_message_resolver.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/helpers.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/conftest.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/01-codebase-hooks.md`
