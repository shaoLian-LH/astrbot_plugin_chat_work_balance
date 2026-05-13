# 初始化插件骨架与入口
## 目的
- 从 helloworld 模板切换为 QQ 官方消息解析插件骨架。
- 建立配置、模型、resolver、service 的最小模块目录。
- 让 `main.py` 只负责注册、依赖组装、QQOFFICIAL 监听和回放编排。

## 前置任务依赖
- 无

## 相关文件位置
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py:1-24`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/metadata.yaml:1-6`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/_conf_schema.json`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/config.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/models.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/resolvers/qq_channel_message_resolver.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/services/resource_analysis_service.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/services/merged_forward_reader.py`

## 可复用内容
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/02-modular-plugin-structure.md:44-63`：复用入口薄、业务下沉到模块的插件分层约束。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/04-plugin-config-schema.md:25-31`：复用 `_special: select_provider` 的 provider 选择器规则。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/05-plugin-config-runtime.md:13-28`：复用 `AstrBotConfig` 注入和读取方式。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/06-listen-message-event-basics.md:28-40`：复用 `QQOFFICIAL` 平台过滤和 `stop_event()` 事件消费模式。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md:3-11`：复用 `event.chain_result(chain)` 被动回复模式。

## 如何执行
- 更新 `metadata.yaml`，移除 helloworld 元数据，声明插件名称、描述、作者、版本和 `support_platforms: [qq_official]`。
- 新增 `_conf_schema.json`，只包含 `image_analysis_provider_id`，类型为 `string`，`_special` 为 `select_provider`，默认值为空字符串。
- 新增 `chat_work_balance/` 包结构和空的 `__init__.py`，放置 `config.py`、`models.py`、`resolvers/`、`services/`。
- 改造 `main.py`，接收 `Context` 与 `AstrBotConfig`，构造配置对象、资源解析服务、合并转发读取器和 `QQChannelMessageResolver`。
- 用 `PlatformAdapterType.QQOFFICIAL` 和 `EventMessageType.ALL` 注册全消息监听；监听器调用 resolver，遍历 `ReplayPlan.chunks` 并逐条 `yield event.chain_result(...)`，成功后 `event.stop_event()`。
- 在监听器异常兜底中记录 traceback，返回短错误说明并停止事件。

## 验收目标
- 仓库不再保留 `/helloworld` 指令和 helloworld 注册信息。
- `main.py` 不直接解析消息组件，只做入口编排和异常兜底。
- `_conf_schema.json` 能被 AstrBot 识别为 provider 选择配置。
- 入口能导入新增包结构，且 QQ 官方消息会被插件完整消费。

## 参考文件
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:3-52`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:83-104`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md:7-14`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/02-modular-plugin-structure.md:7-18`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/04-plugin-config-schema.md:1-6`
