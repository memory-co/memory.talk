# instant — 带时区时间解析 + 取最大

`util/instant.py`。

## 这个场景在测什么

- 比较是**时间序、不是字典序**:异构平台时间戳(毫秒/秒、`+08:00` 偏移)
  解析成带时区 datetime 再取最大,序列化回秒精度 `Z`。
- `last_round_update_time` 的兜底链:无可解析 round 时间戳 → `created_at`
  → `synced_at`。

## 不在这测什么

- 这个值在 session 上怎么维护 → `tests/service/sessions/last_round_update_time/`
- explore 怎么用它切先验/后验 → `tests/service/explores/prior_posterior/`
