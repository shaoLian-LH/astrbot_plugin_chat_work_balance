# 2026-05-14_10-10_forward-message-parsing Orchestration Plan

## Task Order
1. `01_extract_forward_transcript.md`
2. `02_forward_summary_service.md`
3. `03_integrate_resolver_and_verify.md`

## Dependencies
- Slice 1 has no prerequisite.
- Slice 2 depends on accepted commit of slice 1.
- Slice 3 depends on accepted commits of slice 1 and slice 2.

## Search Boundary
- Slice 1:
  - `chat_work_balance/config.py`
  - `_conf_schema.json`
  - `chat_work_balance/services/merged_forward_reader.py`
  - `chat_work_balance/services/resource_analysis_service.py`
  - `tests/test_merged_forward_reader.py`
  - `tests/helpers.py`
- Slice 2:
  - `chat_work_balance/services/forward_summary_service.py`
  - `chat_work_balance/config.py`
  - `chat_work_balance/services/resource_analysis_service.py`
  - `tests/helpers.py`
  - `tests/test_resource_analysis_service.py`
  - `tests/test_forward_summary_service.py`
- Slice 3:
  - `main.py`
  - `chat_work_balance/resolvers/onebot_message_resolver.py`
  - `chat_work_balance/models.py`
  - `tests/test_onebot_message_resolver.py`
  - `tests/test_main.py`
  - accepted content from slice 1 and slice 2

## Agent Naming
- Worker names:
  - `worker-forward-transcript`
  - `worker-forward-summary`
  - `worker-resolver-integration`
- Reviewer names:
  - `review-forward-transcript`
  - `review-forward-summary`
  - `review-resolver-integration`
  - `review-forward-message-task`
- Replacement worker names:
  - `replacement-worker-<slice>-<round>`

## Commit Subjects
- Slice 1: `feat(forward): extract bounded forward transcripts`
- Slice 2: `feat(summary): add forward summary service`
- Slice 3: `feat(resolver): summarize forwarded messages in replay`

## Replacement Rule
- If any reviewer leaves `.slfk/docs/REVIEW-ADVICE.md`, the current worker loses edit ownership immediately.
- Main records `review_advice_rounds`, current owner, and previous owners in `process.md`.
- A fresh replacement worker fixes only the reviewer advice within the original slice scope.
- A fresh reviewer performs `replacement-fix review` before the slice can be accepted.

## Final Review Gate
- All three slices have accepted commits.
- `.slfk/docs/REVIEW-ADVICE.md` is absent.
- Cross-slice integration passes final task review.
- `process.md` stays unstaged and uncommitted.
