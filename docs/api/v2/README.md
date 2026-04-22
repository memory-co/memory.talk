# API Reference (v2)

本地 API，v2 CLI 通过调用这些接口实现功能。所有接口返回 JSON。所有 v2 路由统一以 `/v2` 前缀挂载。

```
Search      POST   /v2/search                   主检索入口（返回带前缀的裸 id）
View        POST   /v2/view                     按 id 读取 card 或 session（按前缀自动判型）
Log         POST   /v2/log                      查一个 card / session 的全生命周期事件

Cards       POST   /v2/cards                    创建 card（自动 embedding、自动默认 link）

Tags        POST   /v2/tags/add                 给 session 加 tag
            POST   /v2/tags/remove              去掉 tag

Links       POST   /v2/links                    创建用户 link

Sessions    POST   /v2/sessions                 ingest / 追加 session（CLI sync 内部用）

Rebuild     POST   /v2/rebuild                  重建 SQLite + FTS + 向量 + 日志
Status      GET    /v2/status                   统计信息
```

## 设计要点

- **无 result_id**：v2 不发行 "追踪 token"——search 直接返回带前缀的裸 id，view / log / tag / link 都直接接受这些 id。"这次 AI 会话读了哪些数据" 由 AI 的 tool-use 对话天然承担（sync 之后完整复原）。
- **ID 前缀约定**：所有对外主键都有类型前缀——`card_<ULID>` / `sess_<ULID>` / `link_<ULID>`。服务端靠前缀零成本判型分发。
- **view / log 自动判型**：`POST /v2/view` 的 `id` 字段可以是 `card_*` 或 `sess_*`，服务端按前缀分发。`tag` 只接受 `sess_*`，`card` 写入返回 `card_*`，`link create` 两端显式带 `type` 字段。
- **HTTP 方法**：`POST + JSON body`——虽然没了 result_id 的 `.` 字符问题，但保持所有 API 用 body 一致性更好（将来扩展字段方便）。只有 `/v2/status` 用 GET。
- **副作用日志**：服务端对所有"写行为"落一份 append-only jsonl（`logs/search.jsonl` / `events.jsonl`）。**没有 `view.jsonl`**——不追踪 view 调用。`POST /v2/rebuild` 可按 jsonl 完整重放 `search_log` 和 `event_log`。
- **无 `server start/stop` API**——起停 API 服务本身只能在 CLI 层做。
- **无 `sync` API**——`sync` 是 CLI 胶水：读平台本地文件 → 调 `POST /v2/sessions` 写入。

## 错误

除非端点另有说明，统一用以下 HTTP 状态码：

| 状态 | 含义 | 响应体 |
|------|------|--------|
| 400 | 参数非法、DSL 解析失败、id 前缀错误、类型不匹配、自环 link 等 | `{"error": "<message>"}` |
| 404 | 对象不存在（id 合法但查不到） | `{"error": "not found"}` |
| 500 | 内部错误 | `{"error": "<message>"}` |

对象的 TTL 在 view 响应里体现（`ttl < 0` 表示已过期的用户 link），**不在 HTTP 状态层过滤**。调用方按需自行处理。

CLI 命令文档见 [../../cli/v2/](../../cli/v2/)，数据结构见 [../../structure/v2/](../../structure/v2/)。
