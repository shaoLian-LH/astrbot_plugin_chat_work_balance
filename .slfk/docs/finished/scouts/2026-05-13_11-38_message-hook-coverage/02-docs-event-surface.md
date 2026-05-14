# 1. Scope

- 仅调查官方 AstrBot 文档与官方仓库源码中，插件接收“全局消息拦截”的公开入口，以及 `aiocqhttp` / OneBot、QQ 官方消息是否经由统一 `AstrMessageEvent` 进入插件层。
- 不做实现、不改产品代码、不替当前项目做最终设计决策。

# 2. Findings with evidence

- 公开的插件消息入口是统一的 `AstrMessageEvent`，官方文档直接写明“消息平台下发的消息会被封装为 `AstrMessageEvent` 传递给插件处理”。
  证据：
  [https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html](https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html)
  对应仓库文档：
  `/tmp/AstrBot-doc-scout/docs/zh/dev/star/guides/listen-message-event.md`

- 插件层可做“全量消息监听”，文档给出的公开方式是 `@filter.event_message_type(filter.EventMessageType.ALL)`；如果只限某平台，再叠 `@filter.platform_adapter_type(...)`。这更像“统一事件面上的全局监听”，不是平台私有 hook。
  证据：
  [https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html](https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html)
  对应仓库文档：
  `/tmp/AstrBot-doc-scout/docs/zh/dev/star/guides/listen-message-event.md`

- `aiocqhttp` / OneBot v11 的插件事件最终确实进入统一 `AstrMessageEvent` 面，而不是单独一套插件 hook。
  证据：
  `class AiocqhttpMessageEvent(AstrMessageEvent):`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py`
  以及适配器把消息统一包成该事件后 `commit_event`：
  `message_event = AiocqhttpMessageEvent(...)`
  `self.commit_event(message_event)`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py`

- OneBot 不仅普通 `message`，连 `notice` 和 `request` 也会先转成 `AstrBotMessage`，再统一走 `AiocqhttpMessageEvent` 提交事件总线。因此从插件入口看，是“同一个事件基类，不同消息内容/类型”，不是额外平台专属插件钩子。
  证据：
  `@self.bot.on_request()`, `@self.bot.on_notice()`, `@self.bot.on_message("group")`, `@self.bot.on_message("private")`
  都调用 `convert_message(...) -> handle_msg(...) -> commit_event(...)`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py`

- QQ 官方平台同样不是单独插件事件面；其事件类也继承 `AstrMessageEvent`，并由平台适配器统一 `commit_event`。
  证据：
  `class QQOfficialMessageEvent(AstrMessageEvent):`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py`
  `self.platform.commit_event(QQOfficialMessageEvent(...))`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py`

- 平台适配器提交的统一事件会进入 `EventBus`，`EventBus.dispatch()` 从队列取出的类型就是 `AstrMessageEvent`。这说明插件层消费面是统一的。
  证据：
  `event: AstrMessageEvent = await self.event_queue.get()`
  `/tmp/AstrBot-doc-scout/astrbot/core/event_bus.py`
  `def commit_event(self, event: AstrMessageEvent) -> None:`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/platform.py`

- 官方公开的“钩子”主要是 LLM/结果装饰/发送后等流程钩子，不是平台消息接入专用钩子；并且文档明确说这些 hook 不能和 `command` / `event_message_type` / `platform_adapter_type` 等监听过滤器叠加在同一个函数上。
  证据：
  [https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html](https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html)
  对应仓库文档：
  `/tmp/AstrBot-doc-scout/docs/zh/dev/star/guides/listen-message-event.md`

- 若插件希望“拦截后阻止后续插件/LLM 流程”，官方公开手段是统一事件上的 `event.stop_event()`，不是平台专属拦截 hook。
  证据：
  `def stop_event(self) -> None:`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/astr_message_event.py`
  文档说明“停止事件传播”：
  [https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html](https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html)

# 3. Options and trade-offs

- 选项 A：只基于统一监听器做覆盖。
  取法：`event_message_type(ALL)` + `platform_adapter_type(AIOCQHTTP | QQOFFICIAL | ...)`。
  取舍：最贴官方公开接口，跨平台一致；但对 OneBot `notice/request` 这类非文本事件，要自己按 `event.message_obj` / `raw_message` 再分流。

- 选项 B：统一监听器为主，必要时下钻平台原始载荷。
  取法：先收 `AstrMessageEvent`，再读 `event.message_obj.raw_message` 判断 OneBot 子类型。
  取舍：兼容官方抽象层与平台差异；但会把业务逻辑部分绑到 OneBot/QQ 官方原始结构，跨平台可移植性下降。

- 选项 C：把“消息监听”和“LLM 前后处理”分成两层。
  取法：消息面用 listener/filter，LLM 面用 `on_waiting_llm_request` / `on_llm_request` / `on_decorating_result`。
  取舍：职责清晰，符合官方模型；但不能把 hook 当作原始消息总入口，且 hook 不能与消息过滤装饰器叠同一函数。

# 4. Risks or unknowns

- 文档虽提供 `EventMessageType.ALL` 示例，但其枚举说明段只明确列出 `PRIVATE_MESSAGE`、`GROUP_MESSAGE`；`ALL` 对 OneBot `notice/request` 的插件匹配行为，最好再以最小实验验证，源码层当前更像“能进总线”，但过滤阶段的最终命中规则这里未完全追到。

- OneBot `notice/request` 被适配成 `AstrBotMessage.type = OTHER_MESSAGE / GROUP_MESSAGE / FRIEND_MESSAGE` 的组合，是否会被现有监听装饰器完整视作“消息事件”处理，需要再看 filter/scheduler 判定细节；本次未继续深挖到完整调度判定代码。

- QQ 官方适配器接入的是频道、群、私聊、C2C 等来源，但插件层公开过滤主要还是平台类型 + 消息类型；如果后续需求要区分“频道 vs 群开放平台群”，仍可能需要读取原始消息对象或 session scene。

# 5. References

- 项目 README：
  `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/README.md`
- AstrBot 插件消息事件文档（中文）：
  [https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html](https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html)
- AstrBot 新建插件文档（中文）：
  [https://docs.astrbot.app/dev/star/plugin-new.html](https://docs.astrbot.app/dev/star/plugin-new.html)
- AstrBot OneBot v11 平台文档（中文）：
  [https://docs.astrbot.app/zh/platform/aiocqhttp.html](https://docs.astrbot.app/zh/platform/aiocqhttp.html)
- 官方仓库：
  [https://github.com/AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot)
- 本地参考仓库文件：
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/astr_message_event.py`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/platform.py`
  `/tmp/AstrBot-doc-scout/astrbot/core/event_bus.py`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py`
  `/tmp/AstrBot-doc-scout/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py`
  `/tmp/AstrBot-doc-scout/docs/zh/dev/star/guides/listen-message-event.md`
