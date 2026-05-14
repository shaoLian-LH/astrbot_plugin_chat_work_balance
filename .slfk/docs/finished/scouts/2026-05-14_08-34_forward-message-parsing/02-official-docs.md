## Scope

- 范围限定为官方资料侦查，不看第三方博客。
- AstrBot 侧优先使用 `docs.astrbot.app`，补充旧版但仍属官方站点的文档页作为交叉证据。
- OneBot 侧使用官方站点对应的官方规范仓库 `botuniverse/onebot-11`。
- 目标只为“新增转发消息解析设计”收集证据，不做实现判断。

## Findings

1. AstrBot 的统一接收入口是 `AstrMessageEvent -> AstrBotMessage`，其中同时保留结构化消息链、纯文本串和适配器原始对象。
   - 当前官方开发文档说明 `AstrMessageEvent` 内含 `message_obj`，而 `AstrBotMessage` 提供：
     - `message: List[BaseMessageComponent]`
     - `message_str: 将消息链中的 Plain 消息连接起来`
     - `raw_message: 原始消息对象`
   - 这意味着：
     - `message` 适合做结构化解析；
     - `message_str` 明确是 Plain 拼接结果，天然会丢掉转发、回复、图片等结构信息；
     - `raw_message` 是适配器原始对象，适合作为 OneBot 特性兜底入口。
   - 证据：
     - https://docs.astrbot.app/dev/star/guides/listen-message-event.html
     - https://docs.astrbot.app/dev/star/resources/astrbot_message.html

2. AstrBot 当前新文档已明确把 OneBot v11 的 `Node` / `Nodes` 视为可接收的消息段类型，但没有在同页显式列出 `Forward`。
   - 当前“处理消息事件”页写明，OneBot v11 额外常见段包括 `Face`、`Node`、`Nodes`、`Poke`。
   - 这能证明 AstrBot 的统一消息链设计至少考虑了“转发节点”这一层。
   - 但这页没有同时列出 `Forward`，所以仅凭当前新文档，不能证明 AstrBot 现在一定把收到的合并转发入口段暴露为 `Forward` 组件。
   - 证据：
     - https://docs.astrbot.app/dev/star/guides/listen-message-event.html

3. AstrBot 官方旧文档明确给出过更完整的组件映射：`reply`、`forward`、`node`、`nodes` 都在消息链类型中。
   - 旧版官方插件开发指南中的 `ComponentTypes` 明确包含：
     - `reply: Reply`
     - `forward: Forward`
     - `node: Node`
     - `nodes: Nodes`
   - 同页还直接建议通过：
     - `print(event.message_obj.raw_message)`
     - `print(event.message_obj.message)`
     来观察“平台原始消息”和“AstrBot 解析后的消息链”。
   - 这说明至少在官方文档设计上，AstrBot 曾明确面向插件暴露过 Reply / Forward / Node / Nodes 这一整组能力。
   - 证据：
     - https://docs.astrbot.app/dev/star/plugin.html

4. AstrBot 官方发送文档已明确支持三类与本设计相关的回复/发送路径。
   - 被动回复：`yield event.plain_result(...)`、`yield event.image_result(...)`、`yield event.chain_result(...)`
   - 主动发送：`self.context.send_message(unified_msg_origin, chains)`
   - 钩子/会话内即时发送：`await event.send(...)`
   - 对转发消息发送，当前官方文档给出 `Node(...)` 示例，并明确“发送群合并转发消息”的当前适配情况为 `OneBot v11`。
   - 这说明发送侧证据是充分的：AstrBot 已把 OneBot v11 合并转发发送能力纳入公开插件接口。
   - 证据：
     - https://docs.astrbot.app/dev/star/guides/send-message.html
     - https://docs.astrbot.app/dev/star/guides/listen-message-event.html
     - https://docs.astrbot.app/dev/star/plugin.html

5. AstrBot 官方文档可证明 OneBot v11 适配器是正式支持项，但没有在接入文档中补充“转发消息接收解析”的行为说明。
   - 官方平台接入页明确 AstrBot 支持接入 OneBot v11 反向 WebSocket 协议端。
   - 但这页只证明“适配器存在且正式支持”，不提供 Forward/Node 在接收侧的投影细节。
   - 证据：
     - https://docs.astrbot.app/platform/aiocqhttp.html

6. OneBot v11 官方规范明确存在 `get_forward_msg`，而且它是公开 API，不是实现私货。
   - 官方公开 API 列表中直接列出 `get_forward_msg 获取合并转发消息`。
   - 接口参数只有 `id`。
   - 响应 `message` 被定义为数组格式消息，且“数组中的消息段全部为 `node` 消息段”。
   - 这已经足够证明：合并转发内容在 OneBot v11 标准里本来就是“通过额外读取接口展开”的。
   - 证据：
     - https://github.com/botuniverse/onebot-11/blob/master/api/public.md#L233-L353

7. OneBot v11 官方规范明确：消息事件里的 `forward` 段只给 `id`，具体内容需要 `get_forward_msg`。
   - 官方 `forward` 段定义只有：
     - `type: "forward"`
     - `data.id`
   - 规范文字直接说明：这个 `id` “需通过 `get_forward_msg` API 获取具体内容”。
   - 这意味着，如果 AstrBot 在接收侧把 OneBot 合并转发保留为 `Forward` 组件，那么仅靠该组件本身不可能拿到完整转发内容，设计上必须联动读取接口。
   - 证据：
     - https://github.com/botuniverse/onebot-11/blob/master/message/segment.md#L541-L553

8. OneBot v11 官方规范明确：自定义 `node` 在接收时不会直接出现在消息事件的 `message` 中，也需要 `get_forward_msg`。
   - 官方“合并转发自定义节点”章节写明：
     - 接收时，这类消息段不会直接出现在消息事件的 `message` 中；
     - 需要通过 `get_forward_msg API` 获取。
   - 这条证据很关键，因为它说明“消息事件里直接看到的链”本身就可能是不完整的。
   - 证据：
     - https://github.com/botuniverse/onebot-11/blob/master/message/segment.md#L567-L603

9. OneBot v11 官方规范里的消息事件本身也同时保留了结构化 `message` 和字符串 `raw_message`，与 AstrBot 的抽象方向一致。
   - 私聊、群聊消息事件均包含：
     - `message`: 结构化消息内容
     - `raw_message`: 原始消息内容字符串
   - 同时消息事件支持快速操作字段 `reply`。
   - 这说明从 OneBot 标准本身看，“结构化解析”和“原始字符串保留”就是并行存在的；AstrBot 的 `message` / `message_str` / `raw_message` 三层抽象并不违背上游标准。
   - 证据：
     - https://github.com/botuniverse/onebot-11/blob/master/event/message.md#L239-L315

10. 基于以上官方证据，可以做一个较稳的设计推断：AstrBot 新增“转发消息解析”时，不能只依赖 `message_str`，也不应假设 `message_obj.message` 一定已经包含完整转发正文。
   - 这是推断，不是文档原句。
   - 根因：
     - `message_str` 只保留 Plain 文本；
     - OneBot `forward` 段本来只给 `id`；
     - OneBot 自定义 `node` 接收时不直接进事件链；
     - AstrBot 当前新文档与旧文档对 `Forward` 是否公开列出存在信息落差。
   - 因此，转发解析设计至少要预留“识别转发入口后调用 `get_forward_msg` 展开”的路径。

## Options

1. 只解析 AstrBot 统一消息链 `event.message_obj.message`
   - 优点：平台无关，最符合 AstrBot 抽象层。
   - 代价：如果 AstrBot 当前版本对 OneBot 合并转发只暴露 `Forward(id)`，或者根本未把完整节点展开到统一链里，这条路会拿不到正文。

2. 以 AstrBot 统一消息链为主，遇到 OneBot 转发入口时补 `get_forward_msg`
   - 优点：兼顾跨平台抽象与 OneBot 特性；和 OneBot 官方规范完全一致。
   - 代价：需要额外依赖 OneBot 动作调用能力，并处理读取失败、权限限制、接口时序等问题。
   - 这是当前证据下最稳的方案。

3. 对 OneBot v11 直接走适配器原始对象解析
   - 优点：信息最全，最接近上游真实语义。
   - 代价：把插件逻辑强绑定到 OneBot 适配器，弱化 AstrBot 的统一抽象；后续平台扩展性最差。

## Risks

- AstrBot 当前新文档没有明确写出收到合并转发时，`event.message_obj.message` 会呈现为 `Forward`、`Node`、`Nodes` 还是别的投影。
- AstrBot 当前新文档和旧文档存在信息落差：
  - 新文档列出 `Node` / `Nodes`
  - 旧文档额外列出 `Forward` / `Reply`
  这说明运行时行为最好再用代码或真实事件做一次验证。
- 官方 AstrBot 文档没有说明插件层是否已有现成的 OneBot `get_forward_msg` 封装；从文档证据看，至少不能先假定它已经存在。
- OneBot 官方规范能证明“应当有 `get_forward_msg`”，但不能保证每个具体 OneBot 实现端在所有场景下都完全一致。

## References

- AstrBot 当前开发文档：处理消息事件  
  https://docs.astrbot.app/dev/star/guides/listen-message-event.html

- AstrBot 当前开发文档：消息的发送  
  https://docs.astrbot.app/dev/star/guides/send-message.html

- AstrBot 当前平台接入文档：接入 OneBot v11 协议实现  
  https://docs.astrbot.app/platform/aiocqhttp.html

- AstrBot 官方旧资源页：AstrBotMessage  
  https://docs.astrbot.app/dev/star/resources/astrbot_message.html

- AstrBot 官方旧插件开发指南  
  https://docs.astrbot.app/dev/star/plugin.html

- OneBot v11 官方规范：公开 API（`get_forward_msg`）  
  https://github.com/botuniverse/onebot-11/blob/master/api/public.md#L233-L353

- OneBot v11 官方规范：消息段类型（`reply` / `forward` / `node`）  
  https://github.com/botuniverse/onebot-11/blob/master/message/segment.md#L527-L603

- OneBot v11 官方规范：消息事件（`message` / `raw_message` / 快速回复 `reply`）  
  https://github.com/botuniverse/onebot-11/blob/master/event/message.md#L239-L315
