# 增加测试与代码级验证
## 目的
- 用假对象覆盖 resolver、服务和入口回放的核心场景。
- 验证初始化后的插件可导入、语法正确、类型检查范围明确。
- 确保设计文档列出的完成标准有可执行证据。

## 前置任务依赖
- `01_initialize_plugin_skeleton.md`
- `02_implement_resolver_and_services.md`

## 相关文件位置
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/tests/`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/AGENTS.md`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/pyproject.toml`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/uv.lock`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/models.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/resolvers/qq_channel_message_resolver.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/services/resource_analysis_service.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/chat_work_balance/services/merged_forward_reader.py`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/main.py`

## 可复用内容
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:116-131`：复用设计文档的 8 个必测场景和完成标准。
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md:7-14`：复用 API 事实构造假对象和断言重点。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/06-listen-message-event-basics.md:35-40`：复用事件消费与 `stop_event()` 断言。
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/08-send-message.md:3-11`：复用 `chain_result` 回放断言。
- `https://docs.astral.sh/uv/concepts/projects/init/`：复用 `uv init` 的项目初始化方式。
- `https://docs.astral.sh/uv/concepts/projects/dependencies/`：复用 `uv` 对 `dependency-groups.dev` 与开发依赖的官方定义。
- `https://docs.astral.sh/uv/reference/cli/`：复用 `uv run --group dev` 与 `--extra` 的官方命令语义。

## 如何执行
- 建立轻量测试假对象，模拟 `AstrMessageEvent`、`message_obj.message`、provider、图片、文件、节点和入口 `chain_result/stop_event` 行为。
- 用 `uv` 初始化当前仓库的项目依赖元数据，补齐 `pyproject.toml`，并生成 `uv.lock`。
- 用 `dependency-groups.dev` 管理测试依赖，不要把 `pytest` 放进 optional extras。
- 覆盖纯文本消息日志和回放。
- 覆盖 `Plain + Image + File` 的逻辑顺序、图片解析文本插入、文件异步获取和 chunk 拆分。
- 覆盖未配置插件 provider 时使用系统默认 provider。
- 覆盖图片 provider 失败仍回放原图、追加失败说明且后续文件不丢失。
- 覆盖 `Nodes/Node` 三层递归、超深截断和混合转发节点中的图片解析。
- 覆盖多图片/多文件混合链的富媒体拆分。
- 覆盖 resolver 未预期异常时入口返回短错误说明并调用 `stop_event()`。
- 按项目约束运行 `rtk proxy uv run --python 3.10 python -m compileall .`、`rtk proxy uv run --group dev --python 3.10 python -m pytest`，并用 `pyright` 限定扫描新增实现与测试文件。

## 验收目标
- 所有新增测试通过。
- Python 语法检查、导入检查、限定范围 pyright 通过。
- 测试不依赖真实 QQ 凭证、真实 AstrBot 服务或真实图片 provider。
- 失败场景有明确断言，避免只验证成功路径。

## 参考文件
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/plans/2026-05-06_21-14_qq-channel-message-resolver-design.md:114-139`
- `/Users/xuemufan/Documents/code/opensource/astrbot_plugin_chat_work_balance/.slfk/docs/scouts/2026-05-12_qq-channel-message-resolver-review/01-astrbot-api-facts.md:22-26`
- `/Users/xuemufan/Documents/code/opensource/slfk-agent-skills/astrbot-plugin-dev/references/03-empty-project-bootstrap.md`
