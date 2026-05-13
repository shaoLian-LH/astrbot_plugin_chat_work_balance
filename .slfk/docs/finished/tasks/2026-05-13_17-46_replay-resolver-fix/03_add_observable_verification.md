# 补齐阶段日志与验证闭环
## 目的
- 让一次消息处理能从日志中定位接收、解析、回放、丢弃、完成和失败阶段。
- 用测试证明双平台入口、LLM provider 参与、replay chunk 回放和关键日志同时成立。

## 前置任务依赖
- `01_enable_dual_qq_official_entry.md`
- `02_enforce_platform_safe_replay_chunks.md`

## 相关文件位置
- `main.py:21-47`
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:247-323`
- `chat_work_balance/services/resource_analysis_service.py:31-159`
- `tests/test_main.py:67-123`
- `tests/test_qq_channel_message_resolver.py:55-185`
- `tests/test_resource_analysis_service.py:12-107`

## 可复用内容
- `chat_work_balance/resolvers/qq_channel_message_resolver.py:281-323`：复用现有 summary 字段来源，拆成阶段化日志上下文。
- `chat_work_balance/services/resource_analysis_service.py:105-152`：复用 provider 成功与降级日志位置。
- `tests/test_main.py:67-123`：复用 monkeypatch logger 的断言方式。
- `tests/test_resource_analysis_service.py:12-107`：复用 provider 成功、base64 fallback 和失败降级测试场景。

## 如何执行
- 增加统一日志字段：`plugin=chat_work_balance`、平台名、`unified_msg_origin`、`message_id`。
- 在入口与 resolver 关键路径输出 `plugin_init`、`message_received`、`message_resolved`、`chunk_replayed`、`dropped_segment`、`message_completed`、`message_failed`。
- 保留 provider 成功或失败结果，并让图片分析失败仍形成可回放文本。
- 补测试断言关键阶段日志、异常日志、dropped 日志和 provider 参与结果。
- 运行 `pyright` 限定相关文件，并运行当前 Python 解释器下的 pytest 相关测试。

## 验收目标
- 单次成功处理至少能定位 `message_received`、`message_resolved`、`chunk_replayed`、`message_completed`。
- provider 失败、组件 dropped 或入口异常时有 `message_failed` 或 `dropped_segment` 记录。
- 相关测试通过，且 pyright 对改动文件无新增错误。

## 参考文件
- `.slfk/docs/plans/2026-05-13_17-34_replay-resolver-fix-design.md:63-79`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md:14-19`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md:59-64`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:202-225`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py:619-692`
