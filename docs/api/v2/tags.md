# Tags API

v2 tag 只作用于 **session**。两个端点都走 POST + body。

## POST /v2/tags/add

```json
{
  "session_id": "sess_187c6576",
  "tags": ["decision", "project:memory-talk"]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `session_id` | 是 | 必须是 `sess_<...>` |
| `tags` | 是 | 要添加的 tag 列表，一次可传多个 |

行为：

- 已存在的 tag **幂等跳过**，不重复添加。
- 每个**真正新增**的 tag 在 log 里产生一条 `tag_added` 事件；已存在（跳过）的不记事件。

响应：

```json
{"status": "ok", "tags": ["decision", "project:memory-talk"]}
```

返回 `tags` 是本次操作之后该 session 上的**全部 tag**，不是增量。

## POST /v2/tags/remove

```json
{
  "session_id": "sess_187c6576",
  "tags": ["decision"]
}
```

- 不存在的 tag 静默跳过，幂等。
- 每个**真正移除**的 tag 在 log 里产生一条 `tag_removed` 事件。

响应：

```json
{"status": "ok", "tags": ["project:memory-talk"]}
```

## 错误

| 情况 | 状态 |
|------|------|
| `session_id` 不以 `sess_` 开头（例如误传 `card_*`） | 400，`type mismatch: tag only applies to sessions` |
| session 不存在 | 404 |
| `tags` 为空数组或非字符串数组 | 400 |
