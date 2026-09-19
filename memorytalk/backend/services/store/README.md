# services/store —— 装配存储

`StoreService(config)` 只做一件事:按 `MEMORY_TALK_STORE` 用 `providers.load_store()` 选出 provider,再按它的族建好三个仓储——`work_repo`(`work/repo.py`)、`user_repo`(`users/repo.py`)、`token_repo`(`auth/repo.py`)。`main.py` 拿它给各个 service 注入仓储。业务层从不直接碰 provider。
