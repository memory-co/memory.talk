# v1_upgrade_from_081

## 测什么

`migrations/v1/up_*` 在面对 0.8.x 的形状时能把它就地搬到 v1:

- **database** —— 拿 0.8.1 的 SQLite(`sessions` 没有 `tags` /
  `location` / `last_round_id` / `indexed_*` 等 0.8.x 后续加的列,
  `cards` 没有 `tags`,`card_stats` 还带着 `recall_count`,留着旧的
  `recall_log` / `rounds_index`)喂给 `up_database`:
  - 缺的列补上,旧表 (`recall_log` / `rounds_index` / `ingest_log`)
    丢掉,`card_stats.recall_count` 拿掉
  - `rounds_index` 里"每个 session 的 max-idx 那条 round_id"被搬到
    `sessions.last_round_id`(数据搬运,不止 schema 翻新)
  - 再跑一次 `up` 不报错(已经全到位时是 no-op)
  - 完全空库直接喂 up 也能跑到 v1(覆盖 catch_up 撞上 stale state
    的极端 case)

- **searchbase** —— 拿 0.8.1 形状的 LanceDB(`cards.card_id`,
  `rounds` 没有 `id`/`_base_id`/`_chunk`)喂给 `up_searchbase`:
  - `cards.card_id` → `id`
  - `rounds` 补 `id` / `_base_id`(都是 `session_id || ':' || idx`
    算出来的)/`_chunk`(常量 0,因为 0.8.x 都是单 chunk)
  - 跑两次不报错;在 fresh backend 上也是 no-op

## 不测什么

- runner 决定调不调 up —— 在 `runner_modes/`
- 从空白建 v1 —— 在 `v1_baseline/`
- 跟 lifespan 拼装 —— 在 `lifespan_integration/`

## fixture

数据库测试用 `aiosqlite.connect(":memory:")` + 手写 0.8.1 DDL,不挂
项目 fixture。searchbase 测试先用 `lancedb.connect_async` 写一个
0.8.1 形状的库,再起 `LocalSearchBackend` 复用同一个 `data_dir` 拿
`admin()`。
