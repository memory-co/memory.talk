# v2_explore — explore schema delta (v1 → v2)

## 这个场景在测什么

v2 给数据库加 explore 子系统的 schema(`docs/works/v3/explore.md`):

- `explores` 表
- `sessions.last_round_update_time` 列
- `cards.explore_id` / `reviews.explore_id` 列
- 对应索引

锁三条:
1. `v2/init_database`(全新装)= v1 快照 + v2 delta → 上述全都在。
2. `v2/up_database`(从 v1 升)给一个 v1 库补上这些。
3. `up_database` 幂等(再跑一次不报错)。

## 不在这测什么

- `last_round_update_time` 的**回填**(从 rounds.jsonl)→ 在 boot 做,见
  `tests/service/sessions/last_round_update_time/`(迁移没有 filesystem handle)。
- explore 的业务逻辑 → `tests/service/explores/`、`tests/api/explores/`。
- v1 基线 schema → `../v1_baseline/`。
