# 2026-05-13_17-46_replay-resolver-fix

1. Enable dual QQ official entry
   - [slice runtime] review_advice_rounds=0 owner=accepted previous_owners=main,worker-slice-01
   - (6138226) fix(entry): support qq official webhook replay
     - main.py
     - metadata.yaml
     - tests/test_main.py

2. Enforce platform-safe replay chunks
   - [slice runtime] review_advice_rounds=0 owner=accepted previous_owners=blocked_on_slice_01,worker-slice-02
   - (399007c) fix(resolver): enforce platform safe replay chunks
     - chat_work_balance/models.py
     - chat_work_balance/resolvers/qq_channel_message_resolver.py
     - tests/test_qq_channel_message_resolver.py

3. Add observable verification
   - [slice runtime] review_advice_rounds=2 owner=accepted previous_owners=blocked_on_slice_02,worker-slice-03,replacement-worker-slice-03-1,replacement-worker-slice-03-2
   - (4f5b97f) fix(observability): add replay stage diagnostics
     - main.py
     - chat_work_balance/resolvers/qq_channel_message_resolver.py
     - chat_work_balance/services/resource_analysis_service.py
     - tests/test_main.py
     - tests/test_qq_channel_message_resolver.py
     - tests/test_resource_analysis_service.py
