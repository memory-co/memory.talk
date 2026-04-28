# test_link_invalid_create

`memory-talk link create <json>` 所有被拒绝的路径。每个 case 都验证:
CLI 非零退出 + stdout 是结构化 JSON 错误 + **SQLite links 表计数不增加**
(事务性:失败不落盘)。

## 场景矩阵

| 测试函数 | 触发点 | 预期错误子串 |
|---|---|---|
| `test_self_loop_rejected` | `source_id == target_id` | `"self-loop"` |
| `test_type_mismatch_rejected` | `source_type="session"` 但 `source_id` 是 `card_*` | `"type mismatch"` / `"prefix"` |
| `test_missing_source_endpoint_rejected` | `source_id="card_does_not_exist"` | `"not found"` |
| `test_missing_target_endpoint_rejected` | `target_id="sess_nonexistent"` | `"not found"` |
| `test_bad_source_prefix_rejected` | `source_id="not-a-valid-id"`(无 v2 前缀) | `"prefix"` / `"type mismatch"` |
| `test_comment_too_long_rejected` | `comment` 长度 > 500(默认 `settings.search.comment_max_length`) | `"too long"` |

## 事务性断言

每个 case 都做:

```python
before = await cli_env.app.state.db.links.count()
# ... invoke CLI with invalid body ...
assert await cli_env.app.state.db.links.count() == before
```

`LinkService.create()` 把所有校验放在 `db.links.insert` 和 `F.write_link` 之前,
只要有任何一步校验漏掉,这个断言就能抓到(一个 link 文件或者 SQLite row 泄漏)。

种子数据里本来就有一条 card → session 的**默认 link**(来自 card 创建),所以
`before` 不是 0。测试比较的是"非法 create 前后,links 表行数不变"——不管基准
计数是多少。

## 覆盖的代码路径(拒绝分支)

- `LinkService._prefix_matches()`:前缀与 type 对齐检查
- `source_id == target_id` self-loop 早拦截
- `comment_max_length` 长度检查
- `_object_exists()` 存在性检查(card/session 分别查各自 repo)
- `LinkServiceError` → FastAPI 400 → CLI `{error}` + exit 1
- `LinkNotFoundError` → FastAPI 404 → CLI `{error}` + exit 1

## 不覆盖的

- JSON body 本身不合法(这交给 CLI 的 `json.JSONDecodeError` 分支,前面
  `cli/card/test_card_invalid_indexes` 类似场景已覆盖等价路径)
- Pydantic 字段类型错(e.g. `source_type="other"`) —— 被 Pydantic 模型在
  反序列化阶段直接拦掉,返回 422 而不是 400;属于框架契约层,不是业务层
