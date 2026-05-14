# OneBot Only 编排计划

## 任务目标
- 将插件运行时代码、入口声明、测试证据从 QQ Official skeleton 收敛为仅支持 OneBot / aiocqhttp。
- 主线程只负责编排、验收、提交和 `process.md` 维护，不直接实现产品代码。

## 依赖顺序
- `01_onebot_resolver.md` -> `02_entrypoint_metadata_docs.md` -> `03_onebot_behavior_tests.md`

## 验收与提交顺序
- 切片 01：运行时代码不再导入或导出 `QQChannelMessageResolver`，resolver 语义与日志收敛为 OneBot。
- 切片 02：入口、metadata、README、CHANGELOG 只声明 OneBot / aiocqhttp，`main.py` 不再引用 QQ Official 平台常量或 resolver 名称。
- 切片 03：UT 证明 OneBot 私聊、群聊、空输出、异常与 resolver 组件解析行为成立，并通过指定 `pyright` / `pytest` 验证。
- 每个切片都必须先经过独立 review；只有 review 通过且 `.slfk/docs/REVIEW-ADVICE.md` 不存在时，主线程才允许提交。
