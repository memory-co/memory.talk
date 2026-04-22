# Search & Result

v2 设计中心是 search——所有读取都从一次 search 起步，拿到 `result_id` 后再调 `view` / `log` / `links` / `tags`。这份文档把 search 的输出物（`SearchLog` / `SearchResult`）和 `result_id` 的语法、生命周期、验证语义一次性钉死。

## 设计动机：Google 链接追踪的本地版

Google 搜索结果页的链接走 `google.com/url?...&ved=<token>`——`ved` 编码 `(query_id, position, time, signature)`，让 Google 能后向归因"这次 click 来自哪次 search 的第几位"。

memory.talk 的 `result_id` 借了同一思路：

- search 调用时，服务端把 `(search_id, kind, rank)` 编进每条结果的 `result_id` 里返回。
- 调用方拿这个 `result_id` 去 view / log / 建 link，服务端可以**反向**追到"这张 card 是因为哪次 search 的第几位被读到 / 被引用 / 被建 link 到的"。
- 所有此类追踪信息落 jsonl，rebuild 可完整重放。

**和 Google 不同**：我们用**结构化 token** 而不是不透明 token。本地 Skill 工具里可调试性 > 不可猜性；安全性靠服务端 `search_result` 表的存在性校验，不靠 token 不可猜。

## SearchLog

每次 `POST /v2/search` 都在服务端追加一行 `SearchLog`。

```json
{
  "search_id": "sch_01K7XABCDEFGHIJK01234",
  "query": "LanceDB 选型",
  "where": "tag = \"decision\" AND source = \"claude-code\"",
  "top_k": 10,
  "created_at": "2026-04-20T14:30:00Z",
  "result_ttl": 2592000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `search_id` | string | `sch_<ULID>`，本次 search 的唯一标识 |
| `query` | string | 检索文本（可空） |
| `where` | string \| null | 元数据 DSL 串（无则 null） |
| `top_k` | integer | 本次请求的 top_k |
| `created_at` | string | ISO 8601 |
| `result_ttl` | integer | 写入时刻生效的 result_id TTL（秒）。从 `settings.search.result_ttl` 拷一份过来——如果之后 settings 改了，**已经发出去的 result_id 仍按写入时刻的 TTL 生效**，不被追溯影响 |

**落库**：
- SQLite `search_log` 表
- `~/.memory-talk/logs/search.jsonl`（append-only，rebuild 真相之源）

## SearchResult

每次 search 同时为它产出的每条命中追加一行 `SearchResult`——这样 rebuild 能完整恢复 `result_id` 的语义，TTL 计时不重置。

```json
{
  "result_id": "sch_01K7XABCDEFGHIJK01234.c1",
  "search_id": "sch_01K7XABCDEFGHIJK01234",
  "kind": "card",
  "rank": 1,
  "target_id": "01jz8k2m...",
  "score": 0.0312,
  "created_at": "2026-04-20T14:30:00Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `result_id` | string | 形如 `{search_id}.{kind}{rank}`，本条命中的 token |
| `search_id` | string | 外键，指向 `SearchLog.search_id` |
| `kind` | string | `card` / `session` |
| `rank` | integer | 同一 (search, kind) 内的排名，从 1 开始 |
| `target_id` | string | 真实指向的 `card_id` 或 `session_id`（**不出现在任何 API 响应里**——只在服务端表里存在，是 result_id → 对象的解析键） |
| `score` | float | 检索打分（hybrid FTS + 向量） |
| `created_at` | string | 同 SearchLog（拷一份方便单表查询） |

**落库**：
- SQLite `search_result` 表（外键到 `search_log`）
- `~/.memory-talk/logs/search.jsonl` 里和它的 SearchLog 行紧挨着追加（一条 SearchLog 后面跟若干条 SearchResult，按 `(search_id, kind, rank)` 分组）

## result_id 语法

```
ULID         := 26-char Crockford-base32 string

search_id    := "sch_" ULID                     # 例：sch_01K7XABCDEFGHIJK01234567

kind         := "c"                              # card
              | "s"                              # session

rank         := positive integer                 # 1-based, 对齐 results 数组位置

result_id    := primary | view_child | log_child

primary      := search_id "." kind rank          # search 直接铸造
                                                  # 例：sch_01K7XAB....c1

view_child   := result_id ".l" subrank           # /v2/view 响应里铸造
                                                  # 例：sch_01K7XAB....c1.l2

log_child    := result_id ".e" subrank           # /v2/log 响应里铸造
                                                  # 例：sch_01K7XAB....s1.e3

subrank      := positive integer                 # 父节点本次响应内的局部序号
```

**子节点可以无限嵌套**：view 的 link 子节点本身也可以再当作父节点喂给 view，view 又会为它的 link 现生 `.l<M>`，这样形成 `....c1.l2.l1` 这样的链条。每加一层就在父节点末尾接 `.l<N>` 或 `.e<N>`。

## 四种形态对照

| 形态 | 谁铸造 | 何时铸造 | SQLite 表 | jsonl | TTL 来源 |
|------|--------|---------|-----------|-------|----------|
| `sch_<ULID>.c<N>` | `/v2/search` | search 调用 | `search_result` | `search.jsonl` | `SearchLog.result_ttl` |
| `sch_<ULID>.s<N>` | `/v2/search` | 同上 | `search_result` | `search.jsonl` | 同上 |
| `<parent>.l<N>` | `/v2/view` | view 现生 | `view_link_child` | `view.jsonl` | 跟父节点同活 |
| `<parent>.e<N>` | `/v2/log` | log 现生 | `log_event_ref` | `events.jsonl` | 跟父节点同活 |

`view_link_child` 表结构：

| 字段 | 说明 |
|------|------|
| `parent_result_id` | 在哪次 view 哪个父节点上现生的 |
| `subrank` | `.l<N>` 里的 N |
| `link_id` | 指向的真实 link |
| `target_kind` / `target_id` | 该 link 对端的类型和真实 id（用于校验通过后分发） |
| `created_at` | 现生时间 |

`log_event_ref` 表结构类似，只是 `subrank` 对应 `.e<N>`，`target_*` 指向事件 detail 里引用的对象。

## 生命周期

### 主节点（search 铸造）

`SearchLog.created_at + result_ttl` 之后过期。过期不删除——`search_log` / `search_result` 表行保留，只是被任何端点读取时返回 `410 expired`。这样 rebuild 可以重放，过期状态可被复现。

### 子节点（view / log 铸造）

子节点**不独立计时**——TTL 等于父节点剩余 TTL。换句话说，子节点的"过期"等价于父节点的"过期"。

理由：子节点是父节点上下文里临时铸造的"短期引用"。父节点都过期了（30 天前的 search 没人理），它的 link 子节点 / event 引用子节点继续可读没有意义。

实现上，校验子节点时：先校验父节点未过期，再查子表存在即可。子表行不带独立的 `expires_at`。

## 验证流程

任何 v2 写端点（`view` / `log` / `cards` / `links` / `tags`）收到 `result_id` 时按以下顺序校验：

1. **语法校验**：能否按上面 grammar 解析？不能 → `400 invalid result_id`。
2. **顶层主节点**：取出最外层的 `search_id`，查 `search_log`：
   - 不存在 → `404 not found`
   - `created_at + result_ttl < now` → `410 expired`
3. **顶层 rank/kind**：按 `(search_id, kind, rank)` 查 `search_result`：
   - 不存在 → `404 not found`
4. **递归子节点**：如果有 `.l<N>` / `.e<N>` 后缀，按 `(parent_result_id, subrank)` 查对应子表：
   - 不存在 → `404 not found`
   - 如果是 `.l<N>` 且对应 link 自身已过期（`link.ttl < 0`） → `410 expired`（断链不追）
5. **取 target**：从最深一级的 `target_id` + `target_kind` 取出真实对象，分发给业务逻辑。
6. **副作用**：view / cards / links / tags 各自的副作用按其文档行为（落 click、刷 TTL、追加事件等）。

## 与其它结构的关系

- `Talk-Card`（[talk-card.md](talk-card.md)）的 `links[].target_result_id` 在 view 响应里就是 `<parent>.l<N>` 形态。
- `Link`（[link.md](link.md)）的 `link_id` 是真实 link 表的主键，不是 result_id；`POST /v2/links` 的 source/target 只接收 result_id，不接收 link_id。
- `Settings`（[settings.md](settings.md)）的 `settings.search.result_ttl` 控制主节点 TTL。
- `Session`（[session.md](session.md)）的 `index` 是 session 内 round 的稳定编号，是 card 写入时引用 round 的键，**和 result_id 是两套独立体系**——一个对内（数据层），一个对外（API 追踪层）。
