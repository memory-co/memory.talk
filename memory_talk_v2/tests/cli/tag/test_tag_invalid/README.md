# test_tag_invalid

`memory-talk tag {add,remove}` 的拒绝路径。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_tag_add_on_card_prefix_rejected` | `tag add card_xxx foo` | 400,tags 只作用于 session |
| `test_tag_add_on_unknown_session_returns_404` | `tag add sess_missing foo` | 404 |
| `test_tag_remove_on_card_prefix_rejected` | `tag remove card_xxx foo` | 400 |
| `test_tag_remove_on_unknown_session_returns_404` | `tag remove sess_missing foo` | 404 |
| `test_tag_add_on_bad_prefix_rejected` | `tag add plain-no-prefix foo` | 400(无前缀,不是 sess_) |

## 覆盖的代码路径

- `SessionService._require_session()`:前缀检查 + 存在性查找
- 前缀非 `sess_` → `SessionServiceError("type mismatch: tag only applies to sessions")` → 400
- session 不存在 → `SessionNotFound(...)` → 404
- CLI 用 `ApiError` 捕获,打 `{error}` JSON,`sys.exit(1)`

## 为什么不测空 tags

Click 层的 `@click.argument("tags", nargs=-1, required=True)` 在 CLI
解析阶段就会拦截空 tags:

```
$ memory-talk tag add sess_xxx
Usage: memory-talk tag add [OPTIONS] SESSION_ID TAGS...
Error: Missing argument 'TAGS...'.
```

属于 Click 框架契约层,不到 API 也不到 service。测也可以,但几乎是测 Click 本身。
