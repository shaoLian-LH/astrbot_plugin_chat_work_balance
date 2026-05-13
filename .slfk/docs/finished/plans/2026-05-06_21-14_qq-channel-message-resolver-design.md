# QQ 频道消息解析器设计

## 1. 架构边界

采用最小模块化基座。插件初始化后由 `main.py` 注册 QQ 官方平台的全消息监听器，监听器只做三件事：确认事件来自 `QQOFFICIAL`，把 `AstrMessageEvent` 交给 `QQChannelMessageResolver`，然后按 resolver 生成的 `ReplayPlan` 分段回给用户。

`QQChannelMessageResolver` 是本期核心类，输入是 `AstrMessageEvent`，读取 `event.message_obj.message` 而不是只读 `event.message_str`，这样不会丢图片、文件、转发节点。它输出两份结果：一份结构化日志摘要给 AstrBot logger，一份按原始顺序组织的 `ReplayPlan`。`ReplayPlan` 不承诺单条 `MessageChain` 原样发送所有组件，而是把解析结果拆成 QQ 官方平台可发送的多个 reply chunk；每个 chunk 用 `event.chain_result(...)` 回放。这样既保留解析顺序，又避开 QQ 官方适配器单条发送时只取第一张图片、第一段语音、第一段视频、第一份文件，并忽略 `At`、`Nodes`、`Forward` 等组件的限制。

图片资源解析供应商用插件配置 `_conf_schema.json` 增加 `select_provider` 字段。解析器在遇到图片资源时把图片转成本地路径或 base64，再交给图片解析 provider 生成简短解析文本。provider 选择优先使用插件配置；如果用户没有指定，则回退到 AstrBot 系统默认图片解析供应商。图片处理结果要进入回放计划，与原图片内容一起按原始顺序表达。混合消息链按原顺序解析，例如 `text -> image -> file -> text -> forward` 会生成同顺序的日志摘要和 `ReplayPlan`，但最终发送会按 QQ 官方平台能力拆成多条消息，而不是依赖单条混合链完整透传。

### 参考资料

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/metadata.yaml`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/06-listen-message-event-basics.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/04-plugin-config-schema.md`
- `https://docs.astrbot.app/dev/star/guides/listen-message-event.html`
- `https://docs.astrbot.app/dev/star/guides/send-message.html`
- `https://docs.astrbot.app/dev/star/guides/plugin-config.html`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md`

## 2. 模块与职责

建议把模板初始化成这个结构：

```text
main.py
_conf_schema.json
metadata.yaml
chat_work_balance/
  __init__.py
  config.py
  models.py
  resolvers/
    __init__.py
    qq_channel_message_resolver.py
  services/
    __init__.py
    resource_analysis_service.py
    merged_forward_reader.py
```

`main.py` 保持很薄：注册插件、接收 `AstrBotConfig`、创建解析器、监听 `QQOFFICIAL` 消息并按 `ReplayPlan` 逐条回放结果。它不直接解析消息链。

`QQChannelMessageResolver` 负责整体编排：遍历 `event.message_obj.message`，按顺序处理 `Plain`、`Image`、`File`、`Node`、`Nodes`、`Forward`、`Reply`、`Unknown` 等组件，生成日志摘要和平台能力感知的回放计划。它不直接调用模型，而是把图片资源交给 `ResourceAnalysisService`。

`ResourceAnalysisService` 负责图片资源解析。它读取配置里的 `image_analysis_provider_id`，遇到图片时先用 AstrBot `Image.convert_to_file_path()` 或 `convert_to_base64()` 归一化资源，再调用图片解析 provider 生成简短描述。provider 选择优先使用插件配置；如果用户没有指定，则使用 AstrBot 系统默认图片解析供应商。调用 provider 时通过 `context.get_provider_by_id(provider_id)` 取得实例，确认是 `Provider` 后调用 `await provider.text_chat(prompt=..., image_urls=[...])`。模型不可用或资源下载失败时，不阻断回放，但回放中仍保留原图片，并附带一段可读的解析失败说明。

`MergedForwardReader` 负责合并转发读取，递归深度最多三层。它把转发内容转成结构化文本摘要，不尝试“原样发送合并转发”，因为官方文档明确合并转发发送主要适配 OneBot v11，QQ 官方不应作为本期验证前提。

`models.py` 放 resolver 输出模型，例如 `ResolvedMessage`、`ResolvedSegment`、`ReplayPlan`、`ReplayChunk`，避免 resolver 返回松散字典。`ReplayPlan` 记录完整解析顺序，`ReplayChunk` 记录一次实际发送需要的 `MessageChain` 和对应的原始组件位置。`config.py` 做配置读取和默认值，避免业务代码到处读裸 key。

### 参考资料

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/02-modular-plugin-structure.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md`
- `https://docs.astrbot.app/dev/star/guides/listen-message-event.html`
- `https://docs.astrbot.app/dev/star/guides/send-message.html`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md`

## 3. 数据流与回放行为

消息入口只接收 `QQOFFICIAL`。解析器从 `event.message_obj.message` 取完整消息链，逐段处理并生成两个产物：`log_summary` 和 `replay_plan`。日志记录消息来源、消息 ID、纯文本、组件类型列表、图片解析结果、文件信息和合并转发摘要；回放由监听器遍历 `ReplayPlan.chunks`，逐条使用 `event.chain_result(...)` 发送。

`Image` 的处理必须等待图片解析完成，再进入回放计划。具体行为是：先生成包含原 `Image` 组件的 chunk，再生成或追加一段 `Plain` 文本作为图片解析结果；如果消息链是 `text -> image -> file`，解析顺序仍是 `text -> image -> image analysis text -> file`，但实际发送允许拆成多条 chunk，避免 QQ 官方单条混合链只保留第一份富媒体。图片解析失败时，仍回放原图，并追加短说明，例如 `Image analysis failed: <reason>`。

`Plain` 直接进入当前文本 chunk；`File` 优先用 `await File.get_file(allow_return_url=True)` 获取可发送资源，回放时单独成 chunk 并记录 `name/url/file`；`Record`、`Video` 保留原组件回放并记录资源存在，同样避免和其他富媒体挤在同一个 QQ 官方发送 chunk 中；`At`、`Face`、`Reply` 只记录，默认不主动补发 `At`，避免频道误打扰；`Unknown` 转成短文本占位，避免消息静默消失。

合并转发读取按 `Nodes -> Node.content -> nested Node/Nodes` 递归，最多三层。内部图片也走图片解析 provider，并在转发摘要中展示解析结果；合并转发本身回放为可读文本摘要，不尝试重发合并转发结构。

QQ 官方平台发送约束是本设计的硬边界：单次发送中，文本会被聚合，图片、语音、视频、文件分别只会取第一份，无法依赖单条 `MessageChain` 原样表达任意复杂混合链。因此 `ReplayPlan` 必须以“解析顺序完整、发送 chunk 可落地”为准：纯文本和摘要可以合并，富媒体默认单独成 chunk，合并转发固定转为文本摘要。

### 参考资料

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/13-astrbot-config.md`
- `https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/astrbot/core/message/components.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md`

## 4. 配置与异常处理

配置只保留本期需要的字段：

```json
{
  "image_analysis_provider_id": {
    "type": "string",
    "_special": "select_provider",
    "description": "Image analysis provider",
    "default": ""
  }
}
```

provider 选择顺序固定为：插件配置的 `image_analysis_provider_id` 优先；为空时读取 AstrBot 全局 `provider_settings.default_image_caption_provider_id`；仍为空或 provider 不可用时，回放原图片并追加失败说明。失败不是静默降级，必须在 logger 中记录资源类型、组件位置、失败阶段和异常摘要，但不打印 base64、token、完整临时路径等敏感或噪声内容。

图片解析是回放计划的一部分，所以它会阻塞当前消息的回放计划生成，确保用户看到的是“原图片 + 解析文本”。如果一条链里有多张图片，按链顺序逐张处理；单张失败不影响后续段落。provider prompt 默认使用 AstrBot 全局 `provider_settings.image_caption_prompt`，插件后续如需自定义 prompt 再增加配置，不在本期扩展。

合并转发读取有三个保护：递归深度最多三层；节点数做上限，避免超长转发刷屏；不认识的嵌套组件用占位文本保留位置。超出深度时记录 `max depth reached`，并在摘要中提示被截断。图片归一化产生的临时路径或压缩文件必须交给 AstrBot 的临时文件跟踪机制或在服务内部清理，避免长时间运行后堆积临时文件。

监听器在成功回放后调用 `event.stop_event()`，避免 QQ 频道消息又进入默认 LLM 流程产生第二次回复。解析器发生未预期异常时，插件仍返回一条短错误说明并停止事件，日志里记录 traceback 方便定位。这个策略以“诊断/回放插件完整消费 QQ 官方消息”为前提；如果后续产品目标变成辅助默认聊天流程，需要单独调整为异常时允许继续事件。

### 参考资料

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/04-plugin-config-schema.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/05-plugin-config-runtime.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/13-astrbot-config.md`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md`

## 5. 验证与完成标准

实现完成后不启动 AstrBot 前端或服务端，只做代码级验证和可运行性验证。基础验证包括：`uv` 环境下 Python 语法检查、可导入检查、针对 resolver 的单元测试或轻量假对象测试。测试不依赖真实 QQ 凭证，用构造出来的 `AstrMessageEvent`/消息组件替身覆盖核心链路。

必须覆盖这些场景：

```text
1. 纯文本消息 -> 原文本回放，日志包含 message_id 和 component list
2. Plain + Image + File -> ReplayPlan 保留 Plain, Image, image analysis text, File 的逻辑顺序，并拆成 QQ 官方可发送 chunks
3. 未配置插件 provider -> 使用系统默认 provider_settings.default_image_caption_provider_id
4. 图片 provider 失败 -> 原图仍回放，追加失败说明，后续 File 不丢失
5. Nodes/Node 合并转发 -> 最多读取三层，超深内容被截断并记录
6. 混合转发节点中的图片 -> 图片解析结果进入转发摘要
7. 多图片/多文件混合链 -> 每个富媒体按 QQ 官方能力拆分发送，不依赖单条 MessageChain 原样透传
8. 解析器未预期异常 -> 用户收到短错误说明，事件 stop
```

完成标准是：模板元数据不再保留 `helloworld`；`support_platforms` 明确声明 `qq_official`；`main.py` 只做注册和入口编排；QQ 消息处理集中在 `QQChannelMessageResolver`；图片解析 provider 选择顺序符合“插件配置优先，系统默认兜底”；`ReplayPlan` 明确区分完整解析顺序和实际发送 chunks；混合消息链、多富媒体拆分、`File.get_file(...)` 异步获取、三层合并转发都有测试或假对象验证；所有新增代码通过语法检查和导入检查。

### 参考资料

- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/03-empty-project-bootstrap.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/06-listen-message-event-basics.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md`
