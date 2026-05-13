# Replay Resolver Fix Orchestration

## Source Of Truth
- `01_enable_dual_qq_official_entry.md`
- `02_enforce_platform_safe_replay_chunks.md`
- `03_add_observable_verification.md`

## Execution Order
1. Finish slice `01_enable_dual_qq_official_entry.md`.
2. After slice 01 is accepted and committed, finish slice `02_enforce_platform_safe_replay_chunks.md`.
3. After slices 01 and 02 are accepted and committed, finish slice `03_add_observable_verification.md`.
4. Run final task review across accepted commits.

## Orchestration Rules
- Main thread owns `PLAN.md`, `process.md`, staging, commits, final acceptance, and review handoff.
- Main thread does not edit production code for this task.
- Each slice must pass `worker -> slice acceptance review -> replacement loop if needed -> commit`.
- Replacement work stays inside the original slice scope and must consume the full latest reviewer advice.
- `process.md` is local runtime state only and must never be staged or committed.
- If `.slfk/docs/REVIEW-ADVICE.md` exists after a review, the reviewed worker loses ownership immediately and a fresh replacement worker takes over.

## Acceptance Gates
- Slice 01: dual platform entry, metadata declaration, and entry tests.
- Slice 02: platform-safe replay chunks, dropped-segment traceability, and resolver tests.
- Slice 03: stage logs, provider observability, combined tests, and scoped pyright.
- Final review: accepted commits integrate cleanly and `.slfk/docs/REVIEW-ADVICE.md` is absent.
