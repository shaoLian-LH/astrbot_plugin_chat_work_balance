# 转发消息解析设计

## 架构设计

采用“抽取层”和“总结层”分离。

抽取层继续由 `MergedForwardReader` 承担，但职责收窄为：识别转发入口、展开 `Forward(id)`、遍历 `Node/Nodes`、按配置裁剪每层节点，并输出结构化 transcript。它不负责调用 LLM，也不直接决定最终自然语言摘要。

新增独立的 `ForwardSummaryService`。它接收 transcript，读取插件级语言处理 provider 配置，调用 `provider.text_chat(prompt=..., image_urls=[])`，把抽取结果压缩成自然语言摘要。图片叶子仍复用现有 `ResourceAnalysisService`，文本总结不复用也不污染图片分析服务。

配置项放入 `ChatWorkBalanceConfig`。抽取策略配置如下：

- `forward_max_depth`：默认 `3`
- `forward_sample_threshold`：默认 `50`
- `forward_sample_head_count`：默认 `30`
- `forward_sample_tail_count`：默认 `20`

语言处理 provider 需要独立配置：

- `message_resolve_provider_id`：插件所有文本/语言解析能力使用的 provider，默认空字符串。

`message_resolve_provider_id` 不能回退到 `image_analysis_provider_id`。图像解析 provider 和语言解析 provider 是不同能力入口：前者用于图片 caption，后者用于转发总结以及后续所有文本/语言解析场景。若 `message_resolve_provider_id` 为空，视为基础配置错误，直接返回明确失败摘要并记录日志。

不新增单独的 `message_resolve_model_id` 插件字段。AstrBot provider 自身负责 base URL、模型名和密钥等模型配置；插件只选择 provider。使用本地 LM Studio 验证时，应在 AstrBot provider 配置中把服务地址设为 `http://localhost:21451/v1`，模型设为 `gemma-4-e4b-it-mlx`，再由 `message_resolve_provider_id` 指向该 provider。

测试版不暴露 `forward_summary_prompt` 配置，使用内置中文 prompt。prompt 要求 LLM 按消息发送者名称、频道 id 和发言维度做个人级总结，输出形态类似：

```text
["我是风"(103945)]
# 核心观点
1. ...
2. ...
# 关键原话
1. ...
2. ...

["水"(412042323)]
# 核心观点
1. ...
2. ...
# 关键原话
1. ...
2. ...
```

抽取层必须先判断当前层节点数是否大于 `forward_sample_threshold`。只有超过阈值时，才抽取前 `forward_sample_head_count` 和后 `forward_sample_tail_count`；未超过阈值时必须完整保留该层，防止少量转发被错误裁剪。裁剪后 transcript 中必须留下明确标记，例如 `Skipped N nodes in this layer`，让 LLM 知道中间内容被省略。

### 引用

- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/02-official-docs.md`
- `chat_work_balance/services/merged_forward_reader.py`
- `chat_work_balance/services/resource_analysis_service.py`
- `chat_work_balance/config.py`
- `main.py`
- https://docs.astrbot.app/dev/star/guides/listen-message-event.html
- https://docs.astrbot.app/dev/star/guides/send-message.html
- https://github.com/botuniverse/onebot-11/blob/master/api/public.md#L233-L353
- https://github.com/botuniverse/onebot-11/blob/master/message/segment.md#L527-L603

## 数据流

`OneBotMessageResolver.resolve(event)` 遇到 `Forward`、`Node`、`Nodes` 时，不再直接把 `MergedForwardReader.summarize()` 的文本作为最终回复，而是执行“抽取”和“总结”两步。

第一步是 `MergedForwardReader.extract(event, component, ...)`。对 `Node/Nodes`，它直接遍历已有结构；对 `Forward(id)`，它通过 OneBot `get_forward_msg` 展开，再把返回的 node payload 解析成内部 transcript；对嵌套转发，它最多递归到 `forward_max_depth` 层；对每一层 node list，它必须先判断节点总数，只有 `count > forward_sample_threshold` 才抽取前后节点，否则完整保留该层。extract 输出包括参与总结的消息、发送者名称、发送者 id、层级、原始顺序、裁剪说明、不可解析内容说明。

第二步是 `ForwardSummaryService.summarize(transcript, unified_msg_origin, source_label)`。它使用内置中文 prompt，调用 `message_resolve_provider_id` 指向的 provider，并返回 LLM 生成的中文个人级总结。如果 provider 未配置、不可用、调用失败或返回空文本，返回明确失败摘要，不静默丢弃。

最终 `OneBotMessageResolver` 仍然把总结结果包装成 `forward_summary` segment 和 text `ReplayChunk`。`main.py` 继续通过 `yield event.chain_result(chunk.chain)` 回发，因此群聊和私聊都沿用现有同会话回复路径。

链路需要使用 AstrBot 的 `logger` 输出基础统计信息，方便用户在平台日志中排查：收到转发入口、`Forward(id)` 展开成功数量、无效内容过滤数量、每层节点总数、是否触发采样、采样保留数量、跳过数量、最终 transcript 条数、LLM provider id、LLM 调用成功/失败、最终摘要字符数。日志应沿用现有 `plugin=chat_work_balance stage=... unified_msg_origin=... message_id=...` 风格，避免输出完整转发正文，也不逐条打印展开失败或无法识别内容。

### 引用

- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/02-official-docs.md`
- `main.py`
- `chat_work_balance/resolvers/onebot_message_resolver.py`
- `chat_work_balance/services/merged_forward_reader.py`
- `chat_work_balance/services/resource_analysis_service.py`
- https://docs.astrbot.app/dev/star/guides/send-message.html
- https://github.com/botuniverse/onebot-11/blob/master/api/public.md#L233-L353

## 错误处理

转发解析遇到单个无效片段时不应把噪声发给用户。`Forward(id)` 展开失败、节点内容无法识别、未知组件无法转换时，抽取层直接过滤这些内容；不把它们写入最终 transcript，也不额外打印逐条失败日志。统计日志只保留聚合数量，例如过滤了多少个无效节点或无法识别组件。

如果抽取完成后完全没有有效内容，抽取层必须抛出明确异常，resolver 记录错误日志，并阻止插件继续处理该条消息。这个场景说明没有可总结的输入，不能继续调用 LLM，也不能发送空摘要。

LLM 总结失败分两类处理。基础配置错误不重试，例如 `message_resolve_provider_id` 为空、provider 不存在、provider 类型不对；这类错误直接返回明确的中文失败摘要并记录日志。非配置错误允许最多三次尝试，例如 provider 调用异常、临时网络错误、返回空文本；每次失败记录聚合日志，最后一次仍失败时返回明确的中文失败摘要。

采样配置要做边界保护：如果 `forward_sample_head_count + forward_sample_tail_count >= forward_sample_threshold`，仍然只在 `count > forward_sample_threshold` 时触发采样；采样触发后保留集合要去重并按原始顺序输出，防止前后窗口重叠导致重复总结。

### 引用

- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/02-official-docs.md`
- `chat_work_balance/resolvers/onebot_message_resolver.py`
- `chat_work_balance/services/merged_forward_reader.py`
- `chat_work_balance/services/resource_analysis_service.py`
- `tests/test_merged_forward_reader.py`
- `tests/test_onebot_message_resolver.py`

## 测试设计

测试分三层覆盖，不只验证 happy path。

`tests/test_merged_forward_reader.py` 覆盖抽取层：`count <= threshold` 时完整保留，证明不会无脑抽取；`count > threshold` 时只保留前 `head_count` 和后 `tail_count`，顺序正确、窗口重叠不重复；最多解析 `forward_max_depth` 层，超过层级的内容不进入 transcript；每一层独立判断是否采样，不能用全局计数误伤子层；`Forward(id)` 通过 fake OneBot client 展开；展开失败、未知组件、无法识别节点被过滤；全部过滤后抛出异常。

`tests/test_forward_summary_service.py` 覆盖总结层：正常调用 `message_resolve_provider_id` 指向的 provider，传入内置中文 prompt 和 transcript；输出按发送者维度组织；`message_resolve_provider_id` 为空、provider 不存在、provider 类型错误时不重试；不会回退到 `image_analysis_provider_id`；非配置错误最多重试三次；三次失败后返回中文失败摘要，并记录失败日志；日志不得包含完整 transcript。

`tests/test_onebot_message_resolver.py` 和 `tests/test_main.py` 覆盖集成层：resolver 把 LLM 摘要作为 `forward_summary` segment 和 text chunk 回放；群聊和私聊仍通过当前事件回发；完全没有有效转发内容时，resolver 抛错，`main.py` 进入现有错误路径并 `stop_event()`；日志包含基础统计字段：转发入口、采样触发、有效条数、provider、摘要长度。

单元验证命令按仓库约束执行：

```bash
rtk proxy uv run --group dev --python 3.10 python -m pytest tests/test_merged_forward_reader.py tests/test_forward_summary_service.py tests/test_onebot_message_resolver.py tests/test_main.py
rtk pyright chat_work_balance/services/merged_forward_reader.py chat_work_balance/services/forward_summary_service.py chat_work_balance/resolvers/onebot_message_resolver.py main.py
```

允许做一次本地 LM Studio 语义质量验证。服务地址为 `http://localhost:21451/v1`，模型为 `gemma-4-e4b-it-mlx`，二者配置在 AstrBot provider 上，再通过 `message_resolve_provider_id` 选择该 provider。构造包含多名发送者、多层转发、采样触发和关键原话的 transcript，请模型输出个人级总结。验证重点不是固定字面值，而是确认输出是否按发送者分组、是否包含核心观点和关键原话、是否没有混淆发送者。如果小模型效果不达标，不能私自升级模型，必须向设计者请求升级模型。

### 引用

- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/02-official-docs.md`
- `tests/test_merged_forward_reader.py`
- `tests/test_onebot_message_resolver.py`
- `tests/test_main.py`
- `tests/helpers.py`
- `AGENTS.md`
