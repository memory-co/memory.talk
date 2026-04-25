# test_refresh

`refresh(expires_at, factor, max_seconds, now)` 给"还活着"的对象续命:把当前剩余
秒数 × factor、不超过 `max_seconds`,作为新的 `expires_at`。**已过期对象不续命**。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_refresh_active_doubles_within_cap` | 剩 100s,factor=2,cap=10000 | 新 TTL = 200s |
| `test_refresh_respects_max_cap` | 剩 10000s,factor=2,cap=15000 | 新 TTL = 15000(被 cap 砍住,不到 20000)|
| `test_refresh_does_not_revive_expired` | 已过期 50s | 原样返回,不变 |

## 覆盖的代码路径

- `util/ttl.py::refresh()`
- 续命公式 `min(remaining * factor, max_seconds)`
- "已过期不续命"的早返回分支

## 为什么过期不续命

链路语义:对象的 TTL 是"在还活着的时候被访问就续命"。如果让过期对象也续命,等于
给死掉的卡片复活,会让 GC 永远清不掉冷数据。
