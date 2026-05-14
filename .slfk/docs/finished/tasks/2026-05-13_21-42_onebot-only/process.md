# OneBot Only

1. OneBot Resolver 语义收敛
   - [slice runtime] review_advice_rounds=0 owner=accepted previous_owners=worker-onebot-resolver,review-onebot-resolver
   - (e8408b4) refactor(resolver): replace qq official resolver with onebot resolver
     - chat_work_balance/resolvers/__init__.py
     - chat_work_balance/resolvers/onebot_message_resolver.py

2. OneBot 入口与声明收敛
   - [slice runtime] review_advice_rounds=0 owner=accepted previous_owners=worker-onebot-entrypoint,review-onebot-entrypoint
   - (203c32d) refactor(entrypoint): restrict plugin to aiocqhttp
     - main.py
     - metadata.yaml
     - README.md
     - CHANGELOG.md

3. OneBot 行为测试证据
   - [slice runtime] review_advice_rounds=0 owner=accepted previous_owners=worker-onebot-tests,review-onebot-tests
   - (a457f16) test(onebot): cover entrypoint and resolver behavior
     - tests/conftest.py
     - tests/helpers.py
     - tests/test_main.py
     - tests/test_onebot_message_resolver.py
