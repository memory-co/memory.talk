# API Reference (v2)

本地 API，v2 CLI 通过调用这些接口实现功能。所有接口返回 JSON。所有 v2 路由统一以 `/v2` 前缀挂载。

```
Search      POST   /v2/search                   主检索入口（返回 result_id）
View        POST   /v2/view                     按 result_id 读取 card 或 session
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

- **读路径统一为"先 search → 再 view/log"**。v2 不暴露按裸 `card_id` / `session_id` / `link_id` 读取的端点；凡是需要定位一个对象，都要先 `POST /v2/search` 拿 `result_id`。**result_id 的语法、生命周期、验证流程见 [../../structure/v2/search-result.md](../../structure/v2/search-result.md)**——所有写端点（view / log / cards / links / tags）的 result_id 校验逻辑都按那里定义。
- **HTTP 方法**：凡是请求体里带 `result_id` 的一律用 `POST + JSON body`——避免 result_id 里的 `.` 字符在 URL path 里和扩展名混淆。只有 `/v2/status` 用 GET。
- **副作用登记**：服务端对所有"写行为"落一份 append-only jsonl（`logs/search.jsonl` / `view.jsonl` / `events.jsonl`），SQLite 表从 jsonl 派生，`POST /v2/rebuild` 可以按 jsonl 完整重放。详见 [rebuild.md](rebuild.md)。
- **无 `server start/stop` API**——这两个是起停 API 服务本身的命令，只能在 CLI 层做。
- **无 `sync` API**——和 v1 一致，`sync` 是 CLI 胶水：读平台本地文件 → 调 `POST /v2/sessions` 写入。

## 错误

除非端点另有说明，统一用以下 HTTP 状态码：

| 状态 | 含义 | 响应体 |
|------|------|--------|
| 400 | 参数非法、DSL 解析失败、类型不匹配、自环 link 等 | `{"error": "<message>"}` |
| 404 | result_id 未知、对象不存在 | `{"error": "not found"}` |
| 410 | result_id 已过期（超出 `settings.search.result_ttl`） | `{"error": "expired"}` |
| 500 | 内部错误 | `{"error": "<message>"}` |

CLI 命令文档见 [../../cli/v2/](../../cli/v2/)，数据结构见 [../../structure/v2/](../../structure/v2/)。
