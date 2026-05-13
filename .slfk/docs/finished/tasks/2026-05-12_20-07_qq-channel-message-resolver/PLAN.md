# QQ 频道消息解析器编排计划

## 执行顺序
1. `01_initialize_plugin_skeleton.md`
2. `02_implement_resolver_and_services.md`
3. `03_add_tests_and_verification.md`

## 依赖关系
- `02_implement_resolver_and_services.md` 依赖 `01_initialize_plugin_skeleton.md` 已通过独立 review 并提交。
- `03_add_tests_and_verification.md` 依赖 `01_initialize_plugin_skeleton.md`、`02_implement_resolver_and_services.md` 已通过独立 review 并提交。

## 编排规则
- 主线程只负责派发 subagents、维护 `process.md`、执行独立 review、处理 replacement、最终提交。
- 生产代码仅由 subagents 修改；主线程不直接实现功能代码，除非用户显式终止编排。
- 每个 slice 必须按 `worker -> slice acceptance review -> replacement-fix review（如需要） -> commit` 顺序收口。
- 任一 review 失败或留下 `.slfk/docs/REVIEW-ADVICE.md` 时，原 worker 立即失去该 slice 的编辑所有权，必须改派 replacement worker。
- `process.md` 仅记录运行态、owner 变化、accepted commits；永不纳入 stage 或 commit。

## Slice 划分
### Slice A
- 任务文件：`01_initialize_plugin_skeleton.md`
- 目标：从 hello-world 模板切到 QQ 官方消息解析插件骨架，建立入口、配置和包结构。
- 提交粒度：仅包含骨架与入口编排，不包含 resolver/service 核心逻辑。

### Slice B
- 任务文件：`02_implement_resolver_and_services.md`
- 目标：实现 resolver、资源解析服务、合并转发读取器和结构化 replay 模型。
- 提交粒度：仅包含解析与资源服务实现，以及为接入这些实现所需的最小入口调整。

### Slice C
- 任务文件：`03_add_tests_and_verification.md`
- 目标：建立假对象测试并完成 compileall、pytest、限定范围 pyright 验证。
- 提交粒度：测试文件，以及仅在测试暴露真实缺陷时所需的最小实现修正。

## 统一验收口径
- `.slfk/docs/REVIEW-ADVICE.md` 不存在。
- 当前 slice 的 worker 自检与独立 reviewer 结论一致。
- 验证命令按任务文件要求执行并通过。
- stage 前再次确认 `process.md` 未被纳入。

## 最终总验收
- 三个 slice 均有 accepted commit，并在 `process.md` 记录 `(shortHash) subject`。
- 最终 reviewer 仅检查 accepted commits 的跨 slice 集成、任务级完成标准、提交卫生、`.slfk/docs/REVIEW-ADVICE.md` 缺失状态。
