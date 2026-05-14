# 1. Scope

- 检查范围: repo root。
- 强制优先检查已完成: `main.py`, `metadata.yaml`, `tests/test_main.py`, `tests/conftest.py`。
- 目标: 识别当前插件“消息接入点”与“覆盖缺口”，不改代码、不做最终设计决策。

# 2. Findings with evidence

- 当前运行时只有 1 个插件级消息接入点: `ChatWorkBalancePlugin.on_message`。证据: `main.py:45-50`。
- 该接入点只声明接收 `QQOFFICIAL | QQOFFICIAL_WEBHOOK` 两个平台，metadata 也只暴露这两个平台。证据: `main.py:45-49`, `metadata.yaml:7-9`, `tests/test_main.py:104-142`。
- 该接入点的事件类型过滤是 `ALL`，说明平台内的所有消息类型都会进入同一入口，再由 resolver 按组件分流。证据: `main.py:49-50`。
- `on_message` 本身不做消息组件判定，只负责记录日志、调用 resolver、回放 chunk、`stop_event()`。证据: `main.py:51-105`。
- 实际消息覆盖逻辑集中在 `QQChannelMessageResolver.resolve`，已覆盖组件:
  `Plain`, `Image`, `File`, `Record`, `Video`, `Forward`, `Node`, `Nodes` 为可回放；
  `At`, `Face`, `Reply` 为仅记录 dropped、不回放；
  未知组件降级为文本占位。证据: `chat_work_balance/resolvers/qq_channel_message_resolver.py:92-290`。
- 图片不是只“透传图片”，还会追加一次图片分析文本；转发类 (`Forward/Node/Nodes`) 不透传原结构，只汇总成文本。证据: `chat_work_balance/resolvers/qq_channel_message_resolver.py:107-143`, `260-276`。
- 测试对“插件入口声明”覆盖了平台过滤、metadata 平台声明、成功/失败主路径，但没有断言事件类型过滤器仍为 `ALL`。证据: `tests/test_main.py:104-142`, `145-313`。
- 测试对“resolver 组件覆盖”较完整，已验证:
  纯文本、图片分析插入、多富媒体拆 chunk、转发汇总、`At/Face/Reply` dropped、图片分析失败后继续回放。证据: `tests/test_qq_channel_message_resolver.py:70-320`。
- 测试桩里的 `PlatformAdapterType` 默认只定义了 `QQOFFICIAL`，`QQOFFICIAL_WEBHOOK` 是在 `tests/test_main.py` 里动态补进去的；这意味着 webhook 支持的测试更像“装饰器声明存在性校验”，不是基于真实平台事件对象的行为验证。证据: `tests/conftest.py:37-41`, `tests/test_main.py:27-28`。
- 仓库内未发现第二个插件级入口，例如额外的 `@filter.command`、`@filter.platform_adapter_type(...)` 方法、或其他事件 handler。证据: `main.py:45-50`; 全仓搜索结果仅命中这一处入口声明。

# 3. Options and trade-offs

- 选项 A: 保持“单入口 + resolver 内部分流”。
  取舍: 入口最简单，日志链路集中；但平台过滤、事件过滤、组件覆盖缺口都堆在一个入口后面，回归时更依赖 resolver 测试。
- 选项 B: 把“接入点覆盖”与“组件覆盖”分开治理。
  取舍: 可以分别补“入口声明测试”和“resolver 行为测试”；成本低于改架构，且更适合当前仓库现状。
- 选项 C: 如果后续要扩平台，优先新增平台接入证据而不是先改 resolver。
  取舍: resolver 当前实现明显以 QQ Official 消息组件模型为中心；先扩平台声明但不补平台特有事件样本，容易出现“metadata 支持了，行为没证实”。

# 4. Risks or unknowns

- `QQOFFICIAL_WEBHOOK` 目前只确认“声明接入”，未确认 webhook 事件对象在 `message_obj.message`、`chain_result()`、`plain_result()`、`stop_event()` 上与现有假事件完全一致。证据: `main.py:45-50`, `tests/conftest.py:58-59`, `tests/test_main.py:27-28`。
- `event_message_type(ALL)` 的真实覆盖边界未知: 仓库内没有不同消息类型样本测试，无法确认系统消息、非标准消息、空消息链是否也会经过同一回放路径。证据: `main.py:49-50`, `tests/test_main.py:145-313`。
- dropped 组件当前只覆盖 `At/Face/Reply`。若 AstrBot/QQ Official 后续还有其他组件类型，现状会走“unknown 文本占位”而不是显式 dropped 或显式支持。证据: `chat_work_balance/resolvers/qq_channel_message_resolver.py:206-290`。
- 转发消息当前是“摘要文本化”策略，不是原结构重放；如果目标是保真回放，这里是产品能力边界，不只是测试缺口。证据: `chat_work_balance/resolvers/qq_channel_message_resolver.py:260-276`, `tests/test_qq_channel_message_resolver.py:199-235`。

# 5. References

- `main.py:17-23`
- `main.py:24-50`
- `main.py:51-105`
- `metadata.yaml:1-9`
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:42-90`
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:92-290`
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:293-310`
- `tests/test_main.py:27-28`
- `tests/test_main.py:104-142`
- `tests/test_main.py:145-313`
- `tests/conftest.py:37-41`
- `tests/conftest.py:49-69`
- `tests/test_qq_channel_message_resolver.py:70-125`
- `tests/test_qq_channel_message_resolver.py:127-197`
- `tests/test_qq_channel_message_resolver.py:199-235`
- `tests/test_qq_channel_message_resolver.py:238-320`
