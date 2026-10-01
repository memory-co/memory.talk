# services/store —— 装配存储

`StoreService(config)` 只做装配:work 固定开两个 `SQLite`——`works_db`(`config.works_db`,默认 `<home>/works.db`)和 `worktrace_db`(`config.worktrace_db`,默认 `<home>/worktrace.db`),各一个实例,建好 `work_repo`(`WorkRepo`)和 `trace_repo`(`TraceRepo`)(都在 `work/repo.py`);users / auth 按 `MEMORY_TALK_STORE` 用 `providers.load_store()` 选出 `provider`,建 `user_repo`(`users/repo.py`)和 `token_repo`(`auth/repo.py`)。`main.py` 把同一份 `work_repo` 交给 `WorkService`、`MetasService`(投递收件箱)、`UserService`(统计),`trace_repo` 交给 `WorkService` 和 `UserService`。业务层从不直接碰 provider。
