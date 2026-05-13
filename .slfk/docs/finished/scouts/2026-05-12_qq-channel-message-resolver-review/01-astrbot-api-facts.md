## Scope

核对 QQ 频道消息解析器设计依赖的 AstrBot 事件、消息组件、QQ 官方发送适配器、provider/config 事实；不评估产品方向，不实现代码。

## Findings

- 当前仓库仍是 hello-world 模板：`main.py` 只注册 `/helloworld` 指令，`metadata.yaml` 仍是 `helloworld` 元数据，设计属于从模板重建插件而非增量改动。
- AstrBot 完整消息链应从 `event.message_obj.message` 读取，`event.chain_result(chain)` 接收 `list[BaseMessageComponent]`；`event.stop_event()` 可终止后续处理。
- 平台过滤有正式枚举 `PlatformAdapterType.QQOFFICIAL`，adapter key 是 `qq_official`，`EventMessageType.ALL` 可覆盖群/私聊/其他消息类型。
- `Image.convert_to_file_path()` / `convert_to_base64()` 存在；`File.file` 在异步上下文可能返回空并警告，应优先使用 `await File.get_file()`。
- AstrBot 全局默认图片转述配置在 `provider_settings.default_image_caption_provider_id`，默认 prompt 在 `provider_settings.image_caption_prompt`；可通过 `context.get_config(umo).get("provider_settings", {})` 读取。
- 图片转述 provider 的实际调用模式是 `context.get_provider_by_id(provider_id)` 后确认是 `Provider`，再调用 `await provider.text_chat(prompt=..., image_urls=[...])`。
- QQ 官方发送适配器 `_parse_to_qqofficial` 会把整条链聚合为文本，并且只取第一张图片、第一条语音、第一段视频、第一份文件；`At`、`Nodes`、`Forward` 等不在发送解析范围内，会被忽略。
- QQ 官方 Guild/DM 场景发送图片使用 `file_image`，Group/C2C 通过上传 media 发送；合并转发发送主要不是 QQ 官方平台能力。

## Options

- 推荐：把“按原顺序回放 MessageChain”改成“解析按原顺序，发送按 QQ 官方能力生成一个或多个 reply chunks”，每个 chunk 避免超过一个富媒体类型，摘要文本显式保留原始顺序。
- 备选：只回放文本摘要，不回发原始富媒体。实现更稳，但损失“原图/文件一起回放”的目标。
- 不建议：继续承诺单条 `event.chain_result(...)` 原样回放混合链。当前 QQ 官方适配器不会保证这个语义。

## Risks

- 如果设计不改，测试即使用假对象通过，真实 QQ 官方平台仍可能丢第二张图片、第二个文件、At、Forward/Nodes 或打乱用户预期。
- 设计没有明确 provider prompt、超时/并发、图片压缩/临时文件清理策略，真实图片解析可能慢、费用不可控或留下临时文件。
- “解析异常仍 stop event”会吞掉默认 LLM 回复；如果插件定位只是诊断/回放工具，这是合理的，如果定位是业务助手，可能过于强硬。

## References

- `.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md`
- `main.py`
- `metadata.yaml`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/astr_message_event.py`
- `.slfk/tmp/astrbot-src/astrbot/core/message/components.py`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py`
- `.slfk/tmp/astrbot-src/astrbot/core/astr_main_agent.py`
- `.slfk/tmp/astrbot-src/astrbot/core/star/context.py`
- `.slfk/tmp/astrbot-src/astrbot/core/config/default.py`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/03-empty-project-bootstrap.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/04-plugin-config-schema.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/05-plugin-config-runtime.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/06-listen-message-event-basics.md`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md`
