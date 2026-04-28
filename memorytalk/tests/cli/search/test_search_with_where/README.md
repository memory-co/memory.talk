# test_search_with_where

`memory-talk search <query> --where <dsl>` —— 带元数据 DSL 过滤的检索场景。

## 关注点

**DSL filter 真的发挥作用** —— 从 CLI `--where` 一路传到 SearchService,编译成
SQLite whitelist,再作为 LanceDB 的 pre-filter 收窄结果。

**不测试**的:
- DSL 语法的完整覆盖(LIKE / IN / AND / reltime 等) —— `util/dsl.py` 自己的 unit
  测试负责
- 排序 / 相关性质量

## 场景

| 测试函数 | 验证什么 |
|---|---|
| `test_where_filter_narrows_session_hits` | 空 query + `tag = "decision"` → 只返回打过该 tag 的 session |
| `test_where_filter_with_nonmatching_tag_returns_empty` | `tag = "nonexistent"` → sessions.count == 0 |
| `test_where_filter_applies_under_keyword_query_too` | query="LanceDB" + `tag = "decision"` → 两份 session 都包含 "LanceDB",但只有 tagged 的通过过滤 |
| `test_malformed_where_returns_400_error` | `where="unknown_field = 'x'"` → CLI 非零 exit,stdout 包含 `{"error": "DSL parse error: ..."}` |

## 种子数据(有意构造)

- 2 个 session,**文本内容都含 "LanceDB"**:
  - `sess_platform-a`:tags = `["decision"]`
  - `sess_platform-b`:tags = `[]`

两份文本都能被关键词 "LanceDB" 匹配上,所以如果 where filter 没生效,
`"LanceDB"` query 会返回两个 session。过滤生效的话,只剩 `sess_platform-a`。

这个设计让**过滤是否真的在起作用**变成一个明确的断言对比,而不是模糊地看
"hits 数对不对"。

## 覆盖的代码路径

- Click `--where` 参数传递
- `cli/search.py` 把 `--where` 填进请求 body(只有非空才填)
- `SearchService._dsl_whitelists()`:
  - `util/dsl.parse()` 解析 DSL
  - `util/dsl.compile_for("sessions", ...)` 编译成 WHERE 片段
  - `SessionRepo.dsl_whitelist()` 执行 SQL 取 session_id 白名单
  - `CardRepo.dsl_whitelist()` 同上(tag 字段是 sessions-only,cards 侧返 None → card_wl=[])
- LanceDB 的 whitelist pre-filter(`hybrid_search_cards` / `fts_search_sessions` 的 `whitelist` 参数)
- 空 query 时走"metadata-only"分支(`sessions_metadata_filtered`)
- DSL 错误路径:`DSLError` → `SearchError` → FastAPI 400 → `ApiError` → CLI `{error: ...}` + exit 1

## 为什么不在这里测 DSL 的全部语法

DSL 语法的所有分支(`=` / `!=` / `LIKE` / `NOT LIKE` / `IN` / `NOT IN` / `AND` /
reltime / 各种错误)在 `memorytalk/tests/unit/test_dsl.py` 里有纯函数级
的穷举测试。这里的 CLI 层只验证**两件事**:

1. DSL 参数被 CLI 正确传下去(非空才入 body)
2. 过滤语义在真实 SQLite + LanceDB 链路里端到端起作用

再覆盖语法就是重复劳动。
