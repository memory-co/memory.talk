# Sessions API

**v4 与 v3 一致** —— session ingest / 列表 / 标签的接口形态、cursor 语义、请求 / 响应体**完全照 v3**,本目录不复制。

**v4 唯一变化**:所有 `/v3/sessions*` 路由挪到 **`/v4/sessions*`** 前缀,行为不变:

```
GET    /v4/sessions                       列 session(多维过滤,只回元数据)
PATCH  /v4/sessions/{session_id}/tags     合并语义改 kv 标签
POST   /v4/sessions/ensure                读 cursor(读前探位)
POST   /v4/sessions/append                append-only ingest 一段新 round
```

> **注明**:该 session 下**新增的 mark 写入端点**(逐 round 注解 → `#…？` 自动建卡)不在本页,见 [`session-marks.md`](session-marks.md)(`POST/GET /v4/sessions/{id}/marks`)。反查「这个 session 启发了哪些卡 / 答案」见 [`card-sessions.md`](card-sessions.md)(`GET /v4/sessions/{id}/cards`)。

> 完整契约(ensure / append 的请求 / 响应、cursor 三元组、`session_id` 前缀归一化、tag 操作符)见 [`../v3/sessions.md`](../v3/sessions.md)。CLI 用法见 [`../../cli/v4/session.md`](../../cli/v4/session.md)。
