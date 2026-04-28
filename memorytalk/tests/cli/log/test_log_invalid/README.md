# test_log_invalid

`memory-talk log <id>` 的错误路径。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_log_bad_prefix_rejected` | `foo_bar_12345`(未知前缀) | 400 + `"invalid id prefix"` |
| `test_log_unprefixed_id_rejected` | `plain-no-prefix`(无前缀) | 400 + `"invalid id prefix"` |
| `test_log_missing_card_returns_404` | `card_nonexistent_id`(前缀合法但不存在) | 404 + `"not found"` |
| `test_log_missing_session_returns_404` | `sess_nonexistent_id` | 404 + `"not found"` |

## 覆盖的代码路径

- `api/log.py::post_log` 的前缀分发:
  - `parse_id()` 抛 `InvalidIdError` → 400
  - 命中 CARD/SESSION 分支后,对应 service 的 `log()` 内部查对象是否存在
    → 不存在抛 `CardNotFound` / `SessionNotFound` → 404
- `cli/log.py` 的 `ApiError` 捕获 → 打结构化 `{error}` JSON + `sys.exit(1)`

`log` 是纯只读操作,不存在事务性问题(没有副作用要回滚)。
