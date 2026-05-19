# API Reference (v3)

本地 API,v3 CLI 通过调用这些接口实现功能。所有接口返回 JSON。所有 v3 路由统一以 `/v3` 前缀挂载。

```
Search      POST   /v3/search                   主检索入口
Recall      POST   /v3/recall                   hook 阶段无意识召回(极简)
Read        POST   /v3/read                     按 id 读取 card 或 session

Cards       POST   /v3/cards                    创建 card(自动 embedding)
Reviews     POST   /v3/reviews                  创建 review(累加 card.stats)

Sessions    POST   /v3/sessions                 ingest 一条 session(sync watcher 内部用)

Sync        POST   /v3/sync/start               启动后端 watcher
            POST   /v3/sync/stop                停止 watcher
            GET    /v3/sync/status              watcher 状态 + 累积 stats + 最近事件

Explore     GET    /v3/explore/pending          列出未被任何 card 引用过的 work session
            GET    /v3/explore/list             列出 explore namespace 下的 session
            GET    /v3/explore/detail/{sid}     某条 explore session 的详情(产出 cards / reviews)

Embedding   POST   /v3/embedding/reembed        触发重算所有 card 的 embedding(setup 内部用)

Status      GET    /v3/status                   统计信息 + provider info
```

## 设计要点

- **无追踪 token**:沿用 v2 的姿态 —— 所有对外主键都是带前缀的裸 id(`card_<ULID>` / `sess_<ULID>` / `review_<ULID>`),不发行 result_id 这类中间凭据。前缀 = 类型,服务端零成本判型分发(`POST /v3/read` 的 `id` 字段按前缀走 card 或 session)。
- **HTTP 方法**:**POST + JSON body** 作为默认;只有读静态状态的端点(`GET /v3/status` / `GET /v3/sync/status` / `GET /v3/explore/...`)用 GET。
- **路径设计**:资源动作明确时用 POST 名词(`/v3/cards`, `/v3/reviews`),状态查询用 GET 名词(`/v3/status`),特殊动作显式 verb 路径(`/v3/sync/start`, `/v3/embedding/reembed`)。不强行 REST 化。
- **追踪存哪**:服务端对 search 落 append-only 审计 jsonl(`logs/search/<UTC 日期>.jsonl`)+ SQLite `search_log` 表;对 card / session / review 的 lifecycle 事件落 `events.jsonl`(每个对象一份)。**v3 不开 `GET /v3/log` 之类的查询入口** —— 审计文件是后端 infra,要看靠 sqlite 直查或离线工具。
- **无 `server start/stop` API**:进程启停只能在 CLI / OS 层做。
- **`POST /v3/sync/*` 是 server 内部 watcher 的开关**,不是 CLI 端拉文件 —— v3 sync 跟 v2 的 sync 完全是两个东西,详见 [sync.md](sync.md)。

## ID 前缀约定

| 对象 | 前缀 | 示例 |
|---|---|---|
| Card | `card_` | `card_01jz8k2m...` |
| Review | `review_` | `review_01jzr5kq...` |
| Session | `sess_` | `sess_187c6576-...` |
| Search 审计 | `sch_` | `sch_01K7XABC...` |

调用方拿到任何前缀化 id 都可以直接喂回任何接受 id 的端点 —— 不需要去前缀 / 加前缀的中间转换。

## 错误

除非端点另有说明,统一用以下 HTTP 状态码:

| 状态 | 含义 | 响应体 |
|---|---|---|
| 400 | 参数非法、DSL 解析失败、id 前缀错、类型不匹配等 | `{"error": "<message>"}` |
| 404 | 对象不存在(id 合法但查不到) | `{"error": "not found"}` |
| 409 | 写入冲突(显式传的 id 已存在) | `{"error": "<id> already exists"}` |
| 500 | 内部错误 | `{"error": "<message>"}` |

**v3 没有"对象过期"概念** —— card 永不过期,沉浮由动力学算;调用方查到的对象一律按"现在还活着"处理,不需要额外的 ttl < 0 / expired 判断。

## 跟 v2 的差异

| 类别 | v2 | v3 |
|---|---|---|
| 读端点 | `POST /v2/view` | `POST /v3/read`(改名,合约不变) |
| 写 card | `POST /v2/cards` 接受 `summary` + `rounds` + `from_search_id` | `POST /v3/cards` 接受 `insight` + `rounds` + `source_cards`(可选) |
| 写 review | 无 | `POST /v3/reviews`(新增) |
| sync | 无 API(CLI 胶水读文件) | `POST /v3/sync/start/stop` + `GET /v3/sync/status`(后端 watcher) |
| explore | 无 API(CLI 读 jsonl) | `GET /v3/explore/{pending,list,detail/...}` |
| `POST /v2/links` | 用户 link 写入 | **删** —— v3 无 link |
| `POST /v2/tags/{add,remove}` | tag 增删 | **删** —— v3 无 tag |
| `POST /v2/log` | 查对象 lifecycle | **删** —— 不开 CLI / API 入口 |
| `POST /v2/rebuild` | 重建索引 | **删** —— 拆成 `POST /v3/embedding/reembed`(仅 dim 改时 setup 内部用) |
| `GET /v2/status` | 统计 | `GET /v3/status`(字段变了,加 reviews / 去 tags / links) |

详细的 CLI 命令文档见 [`../../cli/v3/`](../../cli/v3/),数据结构定义见 [`../../structure/v3/`](../../structure/v3/)。
