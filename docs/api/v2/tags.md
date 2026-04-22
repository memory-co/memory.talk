# Tags API

v2 tag 只作用于 **session**。两个端点都走 POST + body（避免 result_id 里的 `.` 在 URL path 里被解析成扩展名）。

## POST /v2/tags/add

给 search 结果里的某个 session 加 tag。

请求体：

```json
{
  "result_id": "sch_01K7XABC....s1",
  "tags": ["decision", "project:memory-talk"]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `result_id` | 是 | 必须是 session 类型（`.s<N>`） |
| `tags` | 是 | 要添加的 tag 列表，一次可传多个 |

行为：

- 已存在的 tag **幂等跳过**，不重复添加。
- 每个**真正新增**的 tag 在 log 里产生一条 `tag_added` 事件。已存在（跳过）的不记事件。

响应：

```json
{"status": "ok", "tags": ["decision", "project:memory-talk"]}
```

返回 `tags` 是本次操作之后该 session 上的**全部 tag**，不是增量。

## POST /v2/tags/remove

```json
{
  "result_id": "sch_01K7XABC....s1",
  "tags": ["decision"]
}
```

- `result_id` 必须是 session 类型。
- 不存在的 tag 静默跳过，幂等。
- 每个**真正移除**的 tag 在 log 里产生一条 `tag_removed` 事件。

响应：

```json
{"status": "ok", "tags": ["project:memory-talk"]}
```

同样返回移除后的全量 tag。

## 错误

| 情况 | 状态 |
|------|------|
| `result_id` 是 card 类型（`.c<N>`） | 400，`type mismatch: tag only applies to sessions` |
| `result_id` 已过期 | 410，`expired` |
| `result_id` 未知 | 404 |
| `tags` 为空数组或非字符串数组 | 400 |
