# 扩展 QQ Official 双平台入口
## 目的
- 让插件同时命中 `qq_official` 与 `qq_official_webhook`。
- 保持两类入口共用同一个 resolver 与 replay 行为。

## 前置任务依赖
- 无

## 相关文件位置
- `main.py:15-47`
- `metadata.yaml:1-8`
- `tests/test_main.py:67-123`
- `tests/helpers.py:53-77`

## 可复用内容
- `main.py:35-47`：复用现有事件处理、逐 chunk 回放、异常兜底和 `stop_event()` 流程。
- `tests/test_main.py:67-123`：复用入口成功回放与异常路径测试结构。
- `tests/helpers.py:53-77`：复用 `FakeEvent` 记录回放调用与停止状态。

## 如何执行
- 将入口过滤从仅 `QQOFFICIAL` 调整为同时覆盖 `QQOFFICIAL | QQOFFICIAL_WEBHOOK`。
- 在 `metadata.yaml` 的 `support_platforms` 增加 `qq_official_webhook`。
- 补入口测试，断言双平台过滤配置存在、成功路径逐 chunk 回放、异常路径仍返回短错误并停止事件。

## 验收目标
- `main.py` 中平台过滤明确包含 `QQOFFICIAL` 和 `QQOFFICIAL_WEBHOOK`。
- `metadata.yaml` 同时声明 `qq_official` 与 `qq_official_webhook`。
- 入口测试覆盖双平台命中、成功回放、异常兜底和 `stop_event()`。

## 参考文件
- `.slfk/docs/plans/2026-05-13_17-34_replay-resolver-fix-design.md:3-18`
- `.slfk/tmp/astrbot-src/astrbot/core/star/filter/platform_adapter_type.py:9-12`
- `.slfk/tmp/astrbot-src/astrbot/core/star/filter/platform_adapter_type.py:64-73`
- `.slfk/tmp/astrbot-src/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_event.py:1-17`
- `.slfk/docs/scouts/2026-05-13_17-24_replay-resolver-fix-scope/01-scope-and-facts.md:25-36`
