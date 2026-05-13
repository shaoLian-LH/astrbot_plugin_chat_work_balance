# 实现解析器与资源服务
## 目的
- 实现 `QQChannelMessageResolver`、`ResourceAnalysisService`、`MergedForwardReader` 的核心行为。
- 用结构化模型表达完整解析顺序和 QQ 官方可发送 chunks。
- 确保图片、文件、富媒体、合并转发在回放计划中不静默丢失。

## 前置任务依赖
- `01_initialize_plugin_skeleton.md`

## 相关文件位置
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/models.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/config.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/resolvers/qq_channel_message_resolver.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/services/resource_analysis_service.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/services/merged_forward_reader.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`

## 可复用内容
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md:8-13`：复用完整消息链读取、`File.get_file()`、provider 调用和 QQ 官方发送限制事实。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md:20-34`：复用 `MessageChain` 与常见组件构造方式。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/13-astrbot-config.md:20-25`：复用全局默认图片转述 provider 和 prompt 配置位置。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/05-plugin-config-runtime.md:37-42`：复用集中配置读取和避免敏感日志的实践。

## 如何执行
- 在 `models.py` 定义 `ResolvedMessage`、`ResolvedSegment`、`ReplayPlan`、`ReplayChunk`，区分解析顺序和实际发送 chunk。
- 在 `config.py` 集中读取 `image_analysis_provider_id`，并提供全局默认 provider/prompt 的读取辅助。
- 在 `ResourceAnalysisService` 中按“插件配置 provider 优先、系统默认 provider 兜底”的顺序选择 provider；用 `Image.convert_to_file_path()` 或 `convert_to_base64()` 归一化图片后调用 `provider.text_chat(prompt=..., image_urls=[...])`。
- 在 `ResourceAnalysisService` 中处理 provider 不存在、类型不匹配、图片归一化失败、模型调用失败；失败时返回可读失败说明，但不阻断原图回放和后续组件。
- 在 `MergedForwardReader` 中读取 `Nodes -> Node.content -> nested Node/Nodes`，递归最多三层，设置节点数上限，内部图片复用 `ResourceAnalysisService`，超深或未知组件写入摘要占位。
- 在 `QQChannelMessageResolver` 中遍历 `event.message_obj.message`，按顺序处理 `Plain`、`Image`、`File`、`Record`、`Video`、`At`、`Face`、`Reply`、`Node`、`Nodes`、`Forward`、未知组件。
- 按 QQ 官方能力生成 chunks：文本和摘要可合并；图片、文件、语音、视频默认单独 chunk；合并转发固定转为文本摘要；`At` 默认只记录不补发。
- 生成结构化 `log_summary`，包含来源、message_id、组件列表、图片解析结果、文件信息、转发摘要和失败阶段摘要。

## 验收目标
- resolver 从 `event.message_obj.message` 读取完整消息链，而不是只读 `event.message_str`。
- `Plain + Image + File` 的解析顺序保留为文本、原图、图片解析文本、文件，发送 chunks 不依赖单条混合链完整透传。
- 多图片、多文件、多富媒体会拆成 QQ 官方可落地的多个 chunks。
- 图片 provider 失败不会丢原图，也不会阻断后续文件或文本。
- 合并转发最多读取三层，超深和未知组件在摘要中可见。

## 参考文件
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:63-104`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md:16-26`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md:35-42`
- `https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/astrbot/core/message/components.py`
