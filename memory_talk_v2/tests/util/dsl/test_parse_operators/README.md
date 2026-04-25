# test_parse_operators

`LIKE` / `NOT LIKE` / `IN` / `NOT IN` 这一组非 `=` 操作符。

## 场景矩阵

| 测试函数 | 输入 | 验证什么 |
|---|---|---|
| `test_parse_like_and_not_like` | `tag LIKE "proj%" AND tag NOT LIKE "old%"` | `op` 分别为 `"LIKE"` / `"NOTLIKE"` |
| `test_parse_in_and_not_in` | `source IN ("claude-code", "codex") AND tag NOT IN ("draft")` | `value` 是 `list[str]`,`op` 为 `"IN"` / `"NOTIN"` |

## 覆盖的代码路径

- `util/dsl.py` 的 tokenizer:`LIKE`/`NOT`/`IN` 这几个保留字识别
- `IN (..., ...)` 列表语法 → `value: list[str]`
- `NOT LIKE` / `NOT IN` 合并成 `NOTLIKE` / `NOTIN` 单 token

## 为什么 op 写成 `NOTLIKE` 而不是 `NOT_LIKE`

是 `util/dsl.py` 内部约定 —— 把 `NOT LIKE` 两个 token 合并后存成一个 op 字符串,
方便 `compile_for()` 直接 dispatch。换名字会改 dsl 公开契约,这里只**断言现状**,
不重新设计。
