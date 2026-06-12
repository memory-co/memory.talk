# migration 测试 — 按场景组织

每个子目录是**一个场景**:有自己的 `README.md` 写清"在测什么 / 不在
测什么 / 用哪些 fixture",有自己的 `test.py` 装测试用例。结构跟
`tests/searchbase/local/` 对齐。

## 场景一览

| 目录 | 测什么 |
|---|---|
| [`state_persistence/`](state_persistence/) | `MigrationState` 对 `migrations_state.json` 的 load / mark / save:幂等去重、原子写入、坏文件抛错 |
| [`runner_modes/`](runner_modes/) | `MigrationRunner` 模式决策(init_latest / upgrade_from_zero / catch_up)、子系统 handle 缺失时的跳过、单步失败的 state 保留 |
| [`v1_baseline/`](v1_baseline/) | `migrations/v1/init_*` 全量快照:database + searchbase 都能从空白建出 v1 形状,且幂等 |
| [`v1_upgrade_from_081/`](v1_upgrade_from_081/) | `migrations/v1/up_*` 增量:0.8.x 的 SQLite/LanceDB 形状被原地搬到 v1(列增删 + 旧表清理 + `rounds_index → last_round_id` 数据搬运) |
| [`lifespan_integration/`](lifespan_integration/) | 真正经过 FastAPI lifespan 跑一遍:0.8.1 数据根能启动、`/v3/status` 能返回 200、`migrations_state.json` 写齐、二次启动是 no-op |

## 加新场景

1. 新目录 `tests/migration/场景名/`
2. 写 `README.md`:**测什么 / 不测什么 / 用什么 fixture**
3. 写 `test.py`:测试本体
4. 不需要在任何 index 里登记 —— pytest 自动收集
