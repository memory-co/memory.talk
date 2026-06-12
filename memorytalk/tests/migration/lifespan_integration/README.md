# lifespan_integration

## 测什么

把 framework + v1 content + FastAPI lifespan + searchbase + httpx
**全栈拼上**,确认用户场景:

- **0.8.1 → v1 无感升级** —— `data_root` 里事先写好 0.8.1 形状的
  `memory.db` + `vectors/` LanceDB,起 app 后:
  - lifespan 不抛 `SystemExit`
  - `/v3/status` 返回 200
  - `migrations_state.json` 记下 `v1` 对两个 subsystem 都 applied
  - 升级后的 `sessions` 表有 `tags` / `last_round_id`,旧的
    `recall_log` 不在了,`last_round_id` 数据从 `rounds_index` 搬过来了
- **全新装** —— 空 `data_root` 起 app:state 文件里两个 subsystem
  都 applied,且 method 是 `init`(走 init_latest 路径,不是 up)
- **二次启动** —— 同一个 `data_root` 起两次,第二次的 state 跟第一次
  完全一致(catch_up 啥都不动)

## 不测什么

- 子组件:state I/O 在 `state_persistence/`,runner 决策在
  `runner_modes/`,v1 内容在 `v1_baseline/` + `v1_upgrade_from_081/`
- 业务端到端(card / session / search 通路)—— 那些在
  `tests/api/test_writes.py` 等
- 系统级失败注入(磁盘满、db 锁住等)—— 略,生产监控覆盖

## fixture

- `tmp_path` + `monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", ...)`
- 写一个最小的 `settings.json`(dummy embedder + 立即刷新的 index 配置)
- 0.8.1 形状的 SQLite + LanceDB 由模块内 `_seed_081_*` helper 铺
- `create_app(Config())` + `app.router.lifespan_context(app)` 启动
- 业务调用走 `httpx.AsyncClient + ASGITransport`
