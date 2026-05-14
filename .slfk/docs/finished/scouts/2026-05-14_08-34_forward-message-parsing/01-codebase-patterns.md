## Scope

- Inspect only the existing parsing/replay path inside this repo and answer three questions: where the new forward-message parsing rule should attach, which abstractions are already reusable, and what tests should cover.
- Inspected first as requested: `main.py`, `chat_work_balance/resolvers/onebot_message_resolver.py`, `chat_work_balance/services/merged_forward_reader.py`, `chat_work_balance/services/resource_analysis_service.py`, `chat_work_balance/models.py`, `tests/test_merged_forward_reader.py`, `tests/test_onebot_message_resolver.py`, `tests/test_main.py`.
- Also checked supporting evidence in `chat_work_balance/config.py`, `tests/helpers.py`, and `tests/test_resource_analysis_service.py`.
- No product code changed. No formatter ran. No test suite ran.

## Findings

1. The correct attachment point for `最多 3 层转发消息解析、每层超过 50 只取前 30 后 20` is `MergedForwardReader`, not `main.py`.
   - `main.py` only receives the event, calls `self._resolver.resolve(event)`, then replays each returned chunk back through the same event via `event.chain_result(...)`, and finally stops the event. It does not inspect forward structure itself. Evidence: `main.py:63`, `main.py:78`, `main.py:89`.
   - `OneBotMessageResolver` is the orchestration layer that detects `Forward | Node | Nodes`, delegates them to `self._merged_forward_reader.summarize(...)`, stores the result as a `forward_summary` segment, and appends that summary text into the replay text buffer. Evidence: `chat_work_balance/resolvers/onebot_message_resolver.py:260`, `chat_work_balance/resolvers/onebot_message_resolver.py:268`, `chat_work_balance/resolvers/onebot_message_resolver.py:276`.
   - `MergedForwardReader` already owns the recursive walk, current depth bound, node truncation state, and leaf rendering. That is where the traversal policy belongs. Evidence: `chat_work_balance/services/merged_forward_reader.py:28`, `chat_work_balance/services/merged_forward_reader.py:41`, `chat_work_balance/services/merged_forward_reader.py:66`, `chat_work_balance/services/merged_forward_reader.py:114`.

2. “测试版本总结并发回对应会话” can already reuse the existing replay path as long as the summary is emitted as text chunks.
   - Today the plugin sends output back to the same incoming session by yielding `event.chain_result(chunk.chain)` from `on_message`; this works for both group and private origins in tests. Evidence: `main.py:78`, `tests/test_main.py:169`, `tests/test_main.py:312`.
   - The resolver already models forward output as replayable text, not as a special outbound channel. Evidence: `chat_work_balance/models.py:29`, `chat_work_balance/models.py:43`, `chat_work_balance/resolvers/onebot_message_resolver.py:267`, `chat_work_balance/resolvers/onebot_message_resolver.py:297`.
   - Conclusion: if the “test version summary” is just another text result, the cheapest path is still `MergedForwardReader -> OneBotMessageResolver -> ReplayChunk(text) -> main.py replay`.

3. The reusable abstractions are solid for traversal and image leaves, but there is no existing generic text-summary service.
   - Reusable as-is:
     - recursive forward traversal and indentation: `chat_work_balance/services/merged_forward_reader.py:55`, `chat_work_balance/services/merged_forward_reader.py:171`;
     - leaf-type normalization for plain/image/file/record/video/at/face/reply: `chat_work_balance/services/merged_forward_reader.py:138`;
     - image analysis inside forward leaves via `ResourceAnalysisService.analyze_image(...)`: `chat_work_balance/services/merged_forward_reader.py:149`;
     - source context propagation through `unified_msg_origin` and `source_label`: `chat_work_balance/resolvers/onebot_message_resolver.py:264`, `chat_work_balance/services/resource_analysis_service.py:40`, `chat_work_balance/services/resource_analysis_service.py:177`.
   - `ResourceAnalysisService` currently does provider selection plus image captioning only. It calls `provider.text_chat(prompt=..., image_urls=[...])` and returns `Image analysis: ...`; it does not summarize arbitrary forward text. Evidence: `chat_work_balance/services/resource_analysis_service.py:41`, `chat_work_balance/services/resource_analysis_service.py:90`, `chat_work_balance/services/resource_analysis_service.py:113`, `tests/test_resource_analysis_service.py:15`, `tests/test_resource_analysis_service.py:113`.
   - `ResolvedSegment.metadata` is available if truncation diagnostics need to be preserved without changing replay behavior. Evidence: `chat_work_balance/models.py:8`, `chat_work_balance/models.py:26`.

4. Current behavior exposes two important constraints that should shape the design.
   - The current forward limit is a global visited-node cap (`max_nodes=20`), not a per-layer sampling rule. The new `>50 => first 30 + last 20` policy does not fit the existing `state["visited"]` check and belongs in node-list handling, likely around `_append_nodes(...)`. Evidence: `chat_work_balance/services/merged_forward_reader.py:28`, `chat_work_balance/services/merged_forward_reader.py:84`, `chat_work_balance/services/merged_forward_reader.py:125`.
   - The current text buffer concatenates adjacent text fragments without separators, so forward summaries can stick to neighboring plain text. Existing tests assert this behavior. Evidence: `chat_work_balance/resolvers/onebot_message_resolver.py:70`, `chat_work_balance/resolvers/onebot_message_resolver.py:295`, `tests/test_onebot_message_resolver.py:160`, `tests/test_onebot_message_resolver.py:224`.
   - `Forward(id=...)` is not dereferenced today; it is rendered as `Forward reference: <id>`. If real payloads arrive as forward references instead of expanded nodes, the current chain cannot parse inner content at all. Evidence: `chat_work_balance/services/merged_forward_reader.py:102`.

5. The test gaps are concentrated and map cleanly to three layers.
   - `tests/test_merged_forward_reader.py` should own the traversal policy:
     - exactly-3-layer inclusion vs cut-off semantics;
     - `50` vs `51` node boundaries per layer;
     - keeping `0..29` and tail `-20..-1` in order;
     - independent sampling for nested sibling lists, not one global counter;
     - omission/truncation marker text;
     - image analysis only for retained nodes. Existing coverage today only checks nested image analysis and current max-depth truncation. Evidence: `tests/test_merged_forward_reader.py:39`, `tests/test_merged_forward_reader.py:68`.
   - `tests/test_onebot_message_resolver.py` should verify integration:
     - forwarded summaries still become `forward_summary` segments;
     - `ReplayChunk` ordering and `source_indexes` stay correct with adjacent text/media;
     - multiple forward components do not break chunk boundaries;
     - any new truncation note survives resolver buffering. Existing coverage already proves the resolver delegates forward parsing and emits text-only replay. Evidence: `tests/test_onebot_message_resolver.py:129`, `tests/test_onebot_message_resolver.py:201`, `tests/test_onebot_message_resolver.py:233`.
   - `tests/test_main.py` should verify same-session delivery only if output shape changes:
     - group and private origins still replay the summary to the current event;
     - ordering remains correct if an extra summary chunk is inserted;
     - `stop_event()` still happens exactly once. Existing coverage already proves same-session replay for group/private and empty/error paths. Evidence: `tests/test_main.py:138`, `tests/test_main.py:186`, `tests/test_main.py:277`, `tests/test_main.py:335`.

## Options

- Option A: extend `MergedForwardReader` only.
  - Put the new `3-layer + per-layer 30/20 sampling` policy into node-list traversal, keep resolver/main unchanged, and continue returning plain-text forward summaries.
  - Trade-off: smallest blast radius and best fit with current architecture; still inherits current text-concatenation behavior unless the returned summary text itself includes separators.

- Option B: split “bounded transcript extraction” from “final summary generation”.
  - Keep `MergedForwardReader` responsible for extracting a bounded forward transcript, then let the resolver call a new dedicated summary service.
  - Trade-off: better if “测试版本总结” means an LLM-written summary with its own prompt/provider, but this repo does not currently have a reusable text-summary abstraction, so scope is materially larger than Option A.

- Recommendation:
  - If the requirement is structural parsing plus direct replay, attach in `MergedForwardReader`.
  - If the requirement is true semantic summarization, still attach the bounding logic in `MergedForwardReader`, but do not overload `ResourceAnalysisService`; create a separate summary service above it.

## Risks

- “最多 3 层” is semantically ambiguous against the current `depth >= max_depth` rule: current code traverses depths `0/1/2` and cuts at `3`. The product definition should be aligned to that before implementation. Evidence: `chat_work_balance/services/merged_forward_reader.py:66`.
- The new per-layer sampling rule conflicts with the current global `visited` counter. Keeping both may be useful as a hard safety cap, but they solve different problems. Evidence: `chat_work_balance/services/merged_forward_reader.py:41`, `chat_work_balance/services/merged_forward_reader.py:84`.
- If real OneBot payloads mostly use `Forward(id)` references, current code cannot inspect inner content and would need an additional fetch capability that does not exist in this repo. Evidence: `chat_work_balance/services/merged_forward_reader.py:102`, `tests/test_merged_forward_reader.py:39`, `tests/test_onebot_message_resolver.py:201`.
- If the summary must be sent proactively after the event flow ends, there is no existing abstraction for outbound session send outside `event.chain_result(...)`. Current support is only “reply through the current event”. Evidence: `main.py:78`, `tests/helpers.py:67`, `tests/helpers.py:72`, `tests/helpers.py:76`.

## References

- `main.py:24`
- `main.py:47`
- `main.py:63`
- `main.py:78`
- `main.py:89`
- `chat_work_balance/resolvers/onebot_message_resolver.py:42`
- `chat_work_balance/resolvers/onebot_message_resolver.py:55`
- `chat_work_balance/resolvers/onebot_message_resolver.py:125`
- `chat_work_balance/resolvers/onebot_message_resolver.py:260`
- `chat_work_balance/resolvers/onebot_message_resolver.py:297`
- `chat_work_balance/resolvers/onebot_message_resolver.py:343`
- `chat_work_balance/services/merged_forward_reader.py:25`
- `chat_work_balance/services/merged_forward_reader.py:32`
- `chat_work_balance/services/merged_forward_reader.py:66`
- `chat_work_balance/services/merged_forward_reader.py:84`
- `chat_work_balance/services/merged_forward_reader.py:102`
- `chat_work_balance/services/merged_forward_reader.py:114`
- `chat_work_balance/services/merged_forward_reader.py:138`
- `chat_work_balance/services/resource_analysis_service.py:26`
- `chat_work_balance/services/resource_analysis_service.py:33`
- `chat_work_balance/services/resource_analysis_service.py:40`
- `chat_work_balance/services/resource_analysis_service.py:90`
- `chat_work_balance/services/resource_analysis_service.py:113`
- `chat_work_balance/models.py:7`
- `chat_work_balance/models.py:29`
- `chat_work_balance/models.py:37`
- `chat_work_balance/models.py:43`
- `chat_work_balance/config.py:12`
- `chat_work_balance/config.py:40`
- `chat_work_balance/config.py:53`
- `tests/test_merged_forward_reader.py:39`
- `tests/test_merged_forward_reader.py:68`
- `tests/test_onebot_message_resolver.py:70`
- `tests/test_onebot_message_resolver.py:129`
- `tests/test_onebot_message_resolver.py:201`
- `tests/test_onebot_message_resolver.py:240`
- `tests/test_main.py:138`
- `tests/test_main.py:186`
- `tests/test_main.py:277`
- `tests/test_main.py:335`
- `tests/test_resource_analysis_service.py:15`
- `tests/test_resource_analysis_service.py:62`
- `tests/test_resource_analysis_service.py:113`
- `tests/helpers.py:35`
- `tests/helpers.py:53`
- `tests/helpers.py:67`
