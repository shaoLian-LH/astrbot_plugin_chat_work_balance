# OneBot 入口与声明收敛
## 目的
- `main.py` 只注册 OneBot / aiocqhttp 平台监听。
- 删除 metadata、README、CHANGELOG 中 QQ Official skeleton 定位。
- 保持入口层只负责日志、异常边界、chunk 回放和 `event.stop_event()`。

## 前置任务依赖
- 01_onebot_resolver.md

## 相关文件位置
- main.py:17-105
- metadata.yaml:1-9
- README.md:1-17
- CHANGELOG.md:1-10

## 可复用内容
- main.py:24-35 复用插件初始化和服务装配结构，仅替换 resolver 类型。
- main.py:45-50 复用单入口装饰器结构，仅切换平台过滤到 OneBot / aiocqhttp。
- main.py:51-105 复用入口回放、完成日志、异常消息和 `stop_event()` 流程。
- main.py:108-142 复用统一日志格式、平台提取和摘要截断工具。
- metadata.yaml:1-7 复用基础插件元数据字段。

## 如何执行
- 将 `main.py` 的 resolver import 和实例化切到 OneBot resolver。
- 将 `@filter.platform_adapter_type(...)` 改为 OneBot / aiocqhttp 对应平台枚举，保留 `EventMessageType.ALL`。
- 将启动日志、插件注册描述、metadata 描述改成 OneBot replay 语义。
- 将 `support_platforms` 改为只声明 OneBot 对应平台。
- 更新 README 和 CHANGELOG，不再声称 QQ Official 或双 QQ 平台支持。

## 验收目标
- `main.py` 不再引用 `QQOFFICIAL`、`QQOFFICIAL_WEBHOOK`、`qq_official` 或 `QQChannelMessageResolver`。
- `metadata.yaml` 只声明 OneBot 对应平台。
- README / CHANGELOG 不再描述 QQ Official skeleton。
- 入口成功、空输出、异常路径都会调用 `event.stop_event()`；成功路径按 chunk 顺序 `yield event.chain_result(...)`。

## 参考文件
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:5-12
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:28-39
- .slfk/docs/plans/2026-05-13_21-36_onebot-only-design.md:59-64
- .slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/01-codebase-hooks.md:9-18
- .slfk/docs/scouts/2026-05-13_11-38_message-hook-coverage/02-docs-event-surface.md:8-18
- https://docs.astrbot.app/zh/dev/star/guides/listen-message-event.html
