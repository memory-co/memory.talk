# last_round_update_time — session 时间轴的维护

`IngestService` append + `SessionStore.backfill_last_round_update_time`。

## 这个场景在测什么

- **append 维护**:每次追加 round,把 `last_round_update_time` 推到新旧时间戳
  的(时间)最大值。
- **存量回填**:升级时遍历 rounds.jsonl 一次性填 NULL 行(SQL 迁移没有
  filesystem,boot 时做),幂等。

## 不在这测什么

- 纯时间解析/取最大 → `tests/util/instant/`
- explore 怎么用它切 → `tests/service/explores/prior_posterior/`
