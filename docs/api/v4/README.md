# API Reference (v4)

本地 API，v4 CLI 通过调用这些接口实现功能。所有接口返回 JSON。所有 v4 路由统一以 `/v4` 前缀挂载。

v4 只重做**卡子系统**（被治理的问题图）：一张卡 = **一个问题（Issue）+ 它的若干答案（Position）**，靠对 Position 的 review 顶/踩竞争出"当下用哪个答案"。其余面（sessions / sync / status / embedding）**沿用 v3**，不在本目录重复。

- 机制 / 设计决策见 [`../../works/v4/card.md`](../../works/v4/card.md)
- CLI 使用说明见 [`../../cli/v4/`](../../cli/v4/)
- 数据结构 / schema 见 [`../../structure/v4/`](../../structure/v4/)

```
Recall       POST   /v4/recall                              hook 阶段无意识召回（撞问题 → 取 Position → 现算校验分排序 → 连 scope 注入）
Search       POST   /v4/search                              有意识检索：撞问题 + where DSL，返回卡 + 当下答案
Read         POST   /v4/read                                按 id 读 card_ / pos_ / sess_（前缀判型）

Cards        POST   /v4/cards                               建卡（只一个 issue，不带答案）
             GET    /v4/cards                               列卡（按时间 / 数量）
             POST   /v4/cards/{card_id}/positions           给某卡加一个答案 Position
             GET    /v4/cards/{card_id}/positions           列某卡的所有答案（各带计数 + 现算 credence）
             POST   /v4/cards/{card_id}/links               给某卡建一条 IBIS 边（看边走 /v4/read,无单独列边端点）
             POST   /v4/cards/{card_id}/sessions            给某卡记一条出处（card↔session）
             GET    /v4/cards/{card_id}/sessions            列某卡的出处 session

Reviews      POST   /v4/positions/{position_id}/reviews     对某个 Position 表态（argument ±1/0）

Sessions     GET    /v4/sessions                            列 session（多维过滤，沿用 v3，前缀 /v4）
             PATCH  /v4/sessions/{session_id}/tags          改 session kv 标签（合并语义，沿用 v3）
             POST   /v4/sessions/{session_id}/marks         逐 round 提交 mark（#…？ 自动建 v4 卡）
             GET    /v4/sessions/{session_id}/marks         列这个 session 的 mark
             GET    /v4/sessions/{session_id}/cards         反查：这个 session 启发了哪些卡 / 答案

Status       GET    /v4/status                              健康 + 统计（沿用 v3；reviews_total vestigial 0）
Sync         POST   /v4/sync/{start,stop}                   控制后端 watcher（沿用 v3，前缀 /v4）
             GET    /v4/sync/status                         watcher 状态（沿用 v3，前缀 /v4）
Embedding    （沿用 v3，前缀 /v4）                            配置 / 重算 / 健康
```

> [`POST /v4/read`](read.md) 按 id 前缀判型（`card_` 整卡 / `pos_` 单答案 / `sess_` session）；session 内容沿用 v3 形态。检索走 [`POST /v4/search`](search.md)（撞问题、无沉浮、DSL 换计数字段）。

## 文档清单

| 端点 | 文档 | v4 状态 |
|---|---|---|
| `/v4/recall` | [recall.md](recall.md) | v4 重做 |
| `/v4/search` | [search.md](search.md) | v4 重做 |
| `/v4/read` | [read.md](read.md) | v4 重做 |
| `/v4/cards*` | [cards.md](cards.md) | v4 重做 |
| `/v4/cards/{id}/links` | [card-links.md](card-links.md) | v4 新增 |
| `/v4/cards/{id}/sessions`、`/v4/sessions/{id}/cards` | [card-sessions.md](card-sessions.md) | v4 新增 |
| `/v4/positions/{id}/reviews` | [reviews.md](reviews.md) | v4 重做（target = Position） |
| `/v4/sessions/{id}/marks` | [session-marks.md](session-marks.md) | v4 新增（逐 round 注解） |
| `/v4/sessions`、`/tags`、`/ensure`、`/append` | [sessions.md](sessions.md) | 沿用 v3，前缀 /v4 |
| `/v4/status` | [status.md](status.md) | 沿用 v3，前缀 /v4 |
| `/v4/sync*` | [sync.md](sync.md) | 沿用 v3，前缀 /v4 |
| embedding（配置 / 重算 / 健康） | [embedding.md](embedding.md) | 沿用 v3，前缀 /v4 |
| explore | [explore.md](explore.md) | 下一轮设计，未实施 |

## 设计要点

- **卡 = 问题 + 答案候选**：`POST /v4/cards` 落一个 `issue`（问题文本，检索锚点）；答案是底下的 Position（`claim` 内联）。哪个答案胜出**不靠创建时拍板**，靠对 Position 的 review 顶/踩、按**现算的 credence** 竞争（见 [recall.md](recall.md)）。
- **credence 是现算分、不是字段**：每个 Position 只存 `up_count` / `down_count` / `neutral_count` 三个计数（= 收到 `argument=+1`/`−1`/`0` 的 review 数）；`credence` 是排序时按 `f(up, down)`（`up−down` 或带样本量的 Wilson 下界）算出来的，**不持久化、不在写路径回写**。响应里给出的 `credence` 是服务端现算的派生值。
- **没有"当前答案"状态位**：不设 `accepted` —— 一个 Issue 允许多个 Position 长期并存竞争。"当下用哪个"= 召回时 credence 最高的那个（平手用最近一条 review 时间 tiebreak）。
- **位（scope）是软提示不是门禁**：`scope` 是一句话自由文本（适用场景，可含「不适用于…」），随答案一起注入交给 LLM 自己判语境；**不机械挡卡，跨界默认放行**。相关性只在召回时由检索现算，不回写成字段。
- **三类关系都不内联、可 join、无 FOREIGN KEY**：`card_links`（card↔card，IBIS 边）、`card_sessions`（card↔session，出处）、`reviews`（对 Position 的表态）各自独立。`session_id` 是扁平列，可直接 join（SQLite 是派生索引，容忍悬挂引用，从不加外键约束）。
- **无追踪 token**：所有对外主键都是带前缀的裸 id（`card_<ULID>` / `pos_<ULID>` / `review_<ULID>` / `sess_<ULID>`），不发行中间凭据。前缀 = 类型，服务端零成本判型分发。
- **HTTP 方法**：**POST + JSON body** 默认；只有读列表 / 静态状态的端点（`GET /v4/cards`、各 `GET /v4/cards/{id}/{positions,sessions}`、`GET /v4/sessions/{id}/cards`）用 GET。
- **append-only**：Position 只增不改不删——答案变了不覆盖、不归档，而是**新增一个竞争 Position**；旧答案被踩则 credence 现算掉下去、自然不再被注入，但仍在卡里可查。Review 同样 append-only（表态错了再写一条相反 argument）。

## ID 前缀约定

| 对象 | 前缀 | 示例 |
|---|---|---|
| Card | `card_` | `card_01jz8k2m...` |
| Position | `pos_` | `pos_01jzp3nq...` |
| Review | `review_` | `review_01jzr5kq...` |
| Session | `sess_` | `sess_187c6576-...`（沿用 v3） |

调用方拿到任何前缀化 id 都可以直接喂回任何接受该 id 的端点——不需要去前缀 / 加前缀的中间转换。

## 错误

除非端点另有说明，统一用以下 HTTP 状态码：

| 状态 | 含义 | 响应体 |
|---|---|---|
| 400 | 参数非法、id 前缀错、`argument`/`type` 非法、`indexes` 越界 / 非单调等 | `{"error": "<message>"}` |
| 404 | 对象不存在（id 合法但查不到） | `{"error": "not found"}` |
| 409 | 写入冲突（显式传的 id 已存在） | `{"error": "<id> already exists"}` |
| 500 | 内部错误（如 embedding provider 调用失败） | `{"error": "<message>"}` |

**v4 没有"对象过期"概念**：不建模时间，卡 / Position 一律按"现在还活着"处理（过期如何处理见 [`../../works/v4/card.md`](../../works/v4/card.md) §5 / §12）。

## 跟 v3 的差异

| 类别 | v3 | v4 |
|---|---|---|
| 卡的形态 | 一句 `insight`（陈述） | 一个 `issue`（问题）+ 若干 `Position`（答案候选） |
| 写卡 | `POST /v3/cards`（`insight` + `rounds` + `source_cards`） | `POST /v4/cards`（`issue`，可选首个 Position）+ `POST /v4/cards/{id}/positions` |
| review target | `POST /v3/reviews`，target = `card_id`，字段 `score` | `POST /v4/positions/{pid}/reviews`，target = `position_id`，字段 `argument` |
| 沉浮信号 | `card.stats` 6 计数器 + 沉浮公式（含 read/recall） | Position 只存 up/down/neutral 三计数；credence 现算；read/recall 不进存储 |
| card↔card | `card.source_cards`（内联，2 种 relation） | `card_links` 表（独立，5 种 IBIS type，多值，可指 `pos_`） |
| card↔session | `card.rounds[].session_id` 隐式 | `card_sessions` 表（独立，可 join，支持多 session） |
| 当前答案 | —（一卡一立场） | 召回时 credence 最高的 Position（无 `accepted` 字段） |
| 适用域 | 无 | `scope`（一句话软提示，非门禁） |

**v3 → v4 的改名 / 迁移**（v3 卡整体改名 `insight` 腾出 `card_` 前缀给 v4）见 [`../../works/v4/card.md`](../../works/v4/card.md) §9。沿用 v3 的 `insight` 端点（`/v3/insights`，只读 + 搜索为主）由迁移产生，本目录不覆盖。

详细的 CLI 命令文档见 [`../../cli/v4/`](../../cli/v4/)，数据结构定义见 [`../../structure/v4/`](../../structure/v4/)。
