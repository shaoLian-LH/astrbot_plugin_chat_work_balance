# Forward Summary Service
## 目的
- 新增 `ForwardSummaryService`，只负责把 transcript 压缩成中文个人级总结。
- 使用 `message_resolve_provider_id` 调用文本 provider，不回退到图片 provider。
- 区分配置错误和临时失败，并保证失败摘要明确可见。

## 前置任务依赖
- `01_extract_forward_transcript.md`

## 相关文件位置
- `chat_work_balance/services/forward_summary_service.py`
- `chat_work_balance/config.py:11-61`
- `chat_work_balance/services/resource_analysis_service.py:26-129`
- `tests/helpers.py:12-32`
- `tests/test_resource_analysis_service.py:15-151`
- `tests/test_forward_summary_service.py`

## 可复用内容
- `chat_work_balance/services/resource_analysis_service.py:40-74`：复用 provider id 解析、`get_provider_by_id()` 和 `Provider` 类型校验模式。
- `chat_work_balance/services/resource_analysis_service.py:89-129`：复用 `provider.text_chat(prompt=..., image_urls=...)` 调用和空返回处理思路；本任务固定传 `image_urls=[]`。
- `chat_work_balance/services/resource_analysis_service.py:139-167`：复用失败结果构造和日志入口，但返回文案改为中文总结失败摘要。
- `tests/helpers.py:12-32`：复用 fake provider 响应和异常注入。

## 如何执行
- 新建服务与结果类型，输入为 transcript、`unified_msg_origin`、`source_label`，输出为 LLM 文本或中文失败摘要。
- 内置中文 prompt，不暴露 `forward_summary_prompt` 配置；prompt 要求按发送者名称、发送者 id、发言维度输出核心观点和关键原话。
- `message_resolve_provider_id` 为空、provider 不存在、provider 类型错误时不重试，记录配置错误日志并返回失败摘要。
- provider 调用异常或返回空文本时最多重试三次；每次记录聚合日志，日志不得包含完整 transcript。
- 补齐 `tests/test_forward_summary_service.py`：正常调用、空配置、不存在 provider、错误类型、不回退 `image_analysis_provider_id`、三次重试、空文本失败、日志不泄露 transcript。

## 验收目标
- 正常路径调用 `provider.text_chat(prompt=..., image_urls=[])`，provider id 来自 `message_resolve_provider_id`。
- 配置错误不重试，临时失败最多三次。
- 失败摘要为中文且可直接作为 `forward_summary` 回放。
- 日志包含 provider、调用结果、摘要长度或失败阶段，不包含完整 transcript。

## 参考文件
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:9-44`
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:67-71`
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:90-110`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md:20-28`
- `tests/test_resource_analysis_service.py:15-151`
