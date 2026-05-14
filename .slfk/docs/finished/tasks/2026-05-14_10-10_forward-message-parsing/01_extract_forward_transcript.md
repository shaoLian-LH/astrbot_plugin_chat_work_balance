# 配置与转发 Transcript 抽取
## 目的
- 增加转发抽取配置和独立语言 provider 配置。
- 将 `MergedForwardReader` 收窄为 transcript 抽取层，支持 `Forward(id)` 展开、`Node/Nodes` 遍历、嵌套深度限制和每层采样。
- 过滤单个无效内容；全部无效时抛出明确异常。

## 前置任务依赖
- 无

## 相关文件位置
- `chat_work_balance/config.py:11-61`
- `_conf_schema.json:1-8`
- `chat_work_balance/services/merged_forward_reader.py:25-173`
- `chat_work_balance/services/resource_analysis_service.py:33-39`
- `tests/test_merged_forward_reader.py:14-110`
- `tests/helpers.py:35-50`

## 可复用内容
- `chat_work_balance/config.py:15-26`：复用插件配置读取和字符串规整模式。
- `chat_work_balance/services/merged_forward_reader.py:55-136`：复用递归遍历入口，但替换全局 `visited` 截断为每层采样。
- `chat_work_balance/services/merged_forward_reader.py:138-169`：复用叶子组件归一化逻辑，图片叶子继续调用图片分析服务。
- `chat_work_balance/services/resource_analysis_service.py:177-196`：复用可观测日志字段格式。
- `tests/test_merged_forward_reader.py:14-37`：复用图片分析 stub。

## 如何执行
- 在 `ChatWorkBalanceConfig` 和 `_conf_schema.json` 增加 `forward_max_depth=3`、`forward_sample_threshold=50`、`forward_sample_head_count=30`、`forward_sample_tail_count=20`、`message_resolve_provider_id=""`。
- 设计 transcript 数据结构，保留发送者名称、发送者 id、层级、原始顺序、正文、采样说明和聚合统计。
- 将 `MergedForwardReader.summarize()` 改为 `extract(event, component, ...)` 或兼容包装；`Forward(id)` 通过 OneBot `get_forward_msg` 展开，`Node/Nodes` 直接遍历。
- 每一层先判断 `count > forward_sample_threshold`；触发采样时保留 head/tail 去重后的原始顺序，并写入 `Skipped N nodes in this layer`。
- 遇到展开失败、未知组件、无法识别节点时只计数过滤；抽取后无有效 transcript 时抛出明确异常。
- 补齐 `tests/test_merged_forward_reader.py` 中阈值边界、采样去重、层级限制、逐层独立采样、`Forward(id)` 展开失败和全部过滤异常测试。

## 验收目标
- `count <= threshold` 时完整保留该层；`count > threshold` 时只保留前后窗口且无重复。
- 嵌套最多进入 `forward_max_depth` 层，超出内容不进入 transcript。
- `Forward(id)` 能通过 fake OneBot client 展开；失败只进入聚合统计。
- 完全没有有效内容时不会调用总结层，而是抛出异常。

## 参考文件
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:5-24`
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:46-65`
- `.slfk/docs/plans/2026-05-14_08-34_forward-message-parsing-design.md:84-92`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/01-codebase-patterns.md:10-32`
- `.slfk/docs/scouts/2026-05-14_08-34_forward-message-parsing/02-official-docs.md:61-84`
- `https://github.com/botuniverse/onebot-11/blob/master/api/public.md#L233-L353`
- `https://github.com/botuniverse/onebot-11/blob/master/message/segment.md#L527-L603`
