# QQ Official Replay Resolver 修复型全量替换设计

## 1. Problem Statement

当前插件的产品目标不变，仍然是 replay resolver：从 QQ 平台消息中读取完整消息链，借助 LLM provider 对图片等资源做补充解析，再按照平台可发送能力生成可回放的结果。需要替换旧设计文档的原因，不是插件要扩展成新的产品，而是旧文档建立在过时的平台假设上，已经不能准确描述 AstrBot 最新版本下的运行边界。

这次设计以 `qq_official` 和 `qq_official_webhook` 同时覆盖为前提。两者在 AstrBot 最新版本中是独立的平台枚举，但 webhook 事件类继承同一套 QQ Official 事件发送语义，因此新设计要把它们视为“两个入口、同一类发送约束”的目标平台，而不是两套独立解析器。

本次替换文档只服务于一个确认目标：验证插件确实可以从 QQ 平台接收基础消息类型，结合配置的 LLM provider 对可分析资源做补充说明，并把结果稳定地输出为可检测的 replay 行为。这里的重点不是追求把所有组件原样透传，而是确认“消息被接收、被解析、被记录、被按平台能力回放”这一整条链路在最新 AstrBot 下成立。

导致旧文档失效的关键事实有两个。第一，平台范围已经变化：最新 AstrBot 同时区分 `QQOFFICIAL` 与 `QQOFFICIAL_WEBHOOK`，而当前入口只监听前者。第二，QQ Official 发送端存在明确的组件吞并语义：单次发送只会保留第一张图片、第一段语音、第一段视频、第一份文件，其余不受支持或超出能力边界的组件会被忽略。因此，新设计的核心不再是“如何把 resolver 设计完整”，而是“如何让 replay plan 明确遵守双平台共用的发送约束，并且让运行结果可观测、可验证”。

### References

- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md`
- `main.py`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py`
- `.slfk/tmp/astrbot-src/astrbot/core/star/filter/platform_adapter_type.py`

## 2. Non-Goals

这次替换文档虽然是完整替换旧设计，但范围仍然严格收缩在“让当前版本的 replay resolver 设计重新准确”。因此，已经在仓库中成立、且不是本轮失配根因的内容，不再作为本次设计的重写重点。

首先，这次不重新设计插件骨架。当前仓库已经完成 `main.py -> resolver -> services` 的分层，`config.py`、`models.py`、`resource_analysis_service.py`、`merged_forward_reader.py` 和对应测试也都存在。新文档默认这些模块结构继续保留，除非某个模块直接妨碍双平台监听或 replay chunk 安全发送，否则不把“模块如何拆分”当成设计对象。

其次，这次不重新讨论 provider 选型与资源分析架构。插件已经具备“插件配置优先、全局 provider_settings 兜底”的 provider 选择逻辑，也已经有图片归一化和失败降级行为。新设计只要求这些已有能力继续服务于 replay resolver 的验证目标，也就是确认 QQ 平台消息能够搭配 LLM provider 完成基础资源解析，而不是扩展新的 provider 策略、prompt 体系或多模型编排。

第三，这次不把 merged forward 能力扩写成“原样转发设计”。当前目标仍然是 replay resolver，不是跨平台富媒体透传器。对 `Forward`、`Node`、`Nodes` 的处理，新设计只要求它们继续被读取、摘要、记录，并在必要时转成平台安全的文本结果，而不是承诺在 `qq_official` 或 `qq_official_webhook` 下原样发送 merged forward 结构。

第四，这次不把文档改成“大而全的测试矩阵总规范”。旧计划变大的一个直接原因，是把插件建设、资源分析、日志、转发、测试矩阵全部写成了一份完整方案。新文档只保留与当前失配直接相关的验证要求：双平台入口是否命中、基础消息类型是否进入 resolver、LLM provider 参与的资源分析是否产生结果、replay chunk 是否遵守 QQ Official 发送边界、日志是否足够判断每一步是否发生。

最后，这次不追求“所有组件都必须原样回放”。如果平台发送能力不支持某类组件，新设计允许继续采用摘要、占位或 dropped with log 的方式处理。判断标准是插件能否稳定证明“它看到了这个组件，并按当前平台能力做了明确处理”，而不是聊天窗口里是否出现了与原始链完全一致的视觉结果。

### References

- `.slfk/docs/finished/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md`
- `chat_work_balance/config.py`
- `chat_work_balance/services/resource_analysis_service.py`
- `chat_work_balance/services/merged_forward_reader.py`

## 3. Replay Chunk Contract

新设计的核心契约不是“resolver 看到了哪些组件”，而是“resolver 产出的 `ReplayPlan.chunks` 在 `qq_official` 和 `qq_official_webhook` 下都不会落入发送端吞组件陷阱”。换句话说，`ReplayChunk` 的定义要从“按解析逻辑分段”升级成“按平台发送安全边界分段”。

这两个平台在 AstrBot 最新版本里虽然是不同入口，但最终复用同一类 QQ Official 发送语义。真实发送端会聚合文本，只保留单次发送中的第一张图片、第一段语音、第一段视频和第一份文件，其余不被支持或超出能力边界的组件会被忽略。因此，新设计要求每个 replay chunk 都必须满足单一发送意图，不能把多个富媒体或“富媒体 + 不安全组件组合”塞进同一个 chunk 再赌平台行为。

具体契约如下。连续 `Plain` 仍然可以合并成单个文本 chunk。`Image` 保持“图片本体一个 chunk，分析文本一个后续文本 chunk”的策略，确保图片回放和 provider 解析结果都能显式出现。`File`、`Record`、`Video` 继续各自单独成 chunk，不与其他富媒体合并。`Forward`、`Node`、`Nodes` 仍然不原样回放，而是通过现有 merged forward reader 产出文本摘要，再按普通文本 chunk 发送。

对之前最容易失配的 `At`、`Face`、`Reply`，新设计的判断标准不是“最新组件类存在，所以必须硬发出去”，而是“是否能在双平台下形成稳定、可验证的发送结果”。因此文档要显式把它们分成两类：能安全前缀或独立发送的，进入 replay chunk；不能保证稳定发送语义的，不强行回放，而是要求 resolver 在 `segments` 和日志里明确记录处理结果。这里尤其要避免为了追求“看起来支持更多组件”而把 reply 或 mention 塞进本来安全的媒体 chunk，导致真正发送时被平台忽略。

`ReplayPlan` 仍然保留“完整解析顺序”和“实际发送顺序”的区分。前者用于日志与调试，后者必须完全服从双平台共用的发送契约。文档里应明确允许这两者不一一同形：例如一条原始消息可以被解析成 `Plain -> Image -> ImageAnalysis -> File -> ForwardSummary` 的顺序，但发送时会变成多个平台安全的独立 chunk。这样设计的验收标准就会从“单条链是否原样回放”转成“每个被支持的基础信息是否都进入了稳定的 replay 输出”。

为了让这套契约可观察，关键路径必须补充 AstrBot logger。日志不是附属能力，而是 replay 修复设计的一部分。最少要覆盖 `plugin_init`、`message_received`、`message_resolved`、`chunk_replayed`、`dropped_segment`、`message_completed`、`message_failed` 七个阶段，并统一包含 `plugin=chat_work_balance`、平台名、`unified_msg_origin`、`message_id` 等可检索字段。这样即使某个组件因为平台边界未被实际发送，也能从日志中确认它已经被解析并按设计处理。

### References

- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py`
- `chat_work_balance/resolvers/qq_channel_message_resolver.py`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md`

## 4. Verification

这次替换文档的完成标准不是“代码结构看起来正确”，而是能够在最新 AstrBot 下证明双平台入口、LLM provider 参与解析、replay chunk 回放、关键日志输出四条链路同时成立。因此，验证必须分成代码级验证和运行级验证两层，且两层都要围绕 `qq_official` 与 `qq_official_webhook` 共用的发送边界来设计。

代码级验证首先要求现有测试体系从“只验证 resolver 内部顺序”升级成“同时验证平台监听与可观测性”。入口测试要覆盖双平台过滤命中、resolver 成功回放、异常兜底和 `stop_event()` 行为，并断言关键阶段日志已经产出。resolver 测试要覆盖基础消息类型进入 `segments`、`ReplayPlan.chunks` 符合平台安全边界、图片分析文本进入后续 replay、forward 继续转摘要文本，以及不安全组件被 dropped 或降级时日志中有明确记录。这里不要求单元测试直接驱动真实 QQ 接口，但要求测试断言和真实 `_parse_to_qqofficial` 语义保持一致，避免 FakeEvent 绿了而平台层仍然吞组件。

运行级验证则以“插件确实可以从 QQ 平台搭配 LLM provider 去解析各种基础信息”为唯一目标。最小场景应覆盖：私聊纯文本、群聊纯文本、图片消息、文件消息、语音消息、视频消息、包含 reply 或 mention 的消息、merged forward 或 forward node 消息。对每个场景，不强求聊天窗口表现为原样透传，但必须同时满足四个结果：消息进入插件、LLM provider 在可分析资源上被调用并给出结果或明确失败说明、replay 输出按平台安全 chunk 发出、AstrBot logger 中能看到从接收、解析、回放到结束的完整轨迹。

日志验收本身要作为正式完成条件写进文档。至少要能从 AstrBot 日志中定位到一次消息处理的 `message_received`、`message_resolved`、`chunk_replayed`、`message_completed`；如果中途发生 provider 失败、reply 无法安全回放、或某类组件被平台边界拒绝，还必须有对应的 `message_failed` 或 `dropped_segment` 记录。没有这些日志，就不能算“插件确实达到了预期解析目标”，因为用户无法判断它是没收到消息、没命中监听、没走到 resolver，还是被发送端吞掉了结果。

### References

- `tests/test_main.py`
- `tests/test_qq_channel_message_resolver.py`
- `tests/test_resource_analysis_service.py`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md`
