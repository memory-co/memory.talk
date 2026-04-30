# test_review_list_session_exist

`session_exist` 字段的两种取值:
- ingested(POST /v2/sessions 写过)→ true
- 只在 recall 路径出现 → false

## 做法

1. 直接 ingest 一个 session A(via `app.state.sessions.ingest`)
2. 给 session A 跑一次 recall
3. 给 session B 跑一次 recall(从来没 ingest 过)
4. `review list` 验证 A 是 true、B 是 false
