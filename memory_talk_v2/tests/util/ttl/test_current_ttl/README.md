# test_current_ttl

`current_ttl(expires_at, now)` 计算 ISO 时间戳到 `now` 还剩多少秒,过期返回负数,
`None` 视为 0。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_current_ttl_null_is_zero` | `expires_at=None` | `0` —— "无过期"按 0 处理 |
| `test_current_ttl_positive_remaining` | 100 秒后 | `100` |
| `test_current_ttl_negative_when_expired` | 50 秒前 | `-50` |

## 覆盖的代码路径

- `util/ttl.py::current_ttl()`:`None` 短路、`iso_to_dt` 解析、秒差计算
- 负数返回值的语义:链路里其他函数(如 `refresh`)用负数判断"已过期就不要续命"

## 为什么 None → 0 而不是 None → +∞

`None` 在数据库语义里是"未设置过期",但搜索/排序场景需要一个可比较的数。
0 让"未过期但 TTL 0"的对象排在最末尾的同一档,行为可预期 —— 给 +∞ 反而会让
"明明无过期"的对象优先级飙升,不是想要的。
