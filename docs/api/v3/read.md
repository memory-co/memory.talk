# Read API

## POST /v3/read

按带前缀 id 读取 card 或 session —— 服务端**按 id 前缀自动判型**:`card_*` 走 card 读取,`sess_*` 走 session 读取,其它前缀 400。

CLI 对应 [`read`](../../cli/v3/read.md) 命令。

### 请求体

```json
{"id": "card_01jz8k2m"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `card_<ULID>` 或 `sess_<ULID>` |

### 响应:card

```json
{
  "type": "card",
  "read_at": "2026-05-18T14:32:05Z",
  "card": {
    "card_id": "card_01jz8k2m",
    "insight": "选定 LanceDB 做向量存储",
    "source_cards": [
      {"card_id": "card_01jzaaaa", "relation": "supersedes"},
      {"card_id": "card_01jzbbbb", "relation": "derives_from"}
    ],
    "rounds": [
      {"role": "human", "text": "ChromaDB vs LanceDB?", "session_id": "sess_abc123", "index": 11},
      {"role": "assistant", "text": "推荐 LanceDB 零依赖", "session_id": "sess_abc123", "index": 12}
    ],
    "reviews": [
      {"review_id": "review_01jzr5kq", "session_id": "sess_abc123", "indexes": "20-25", "score": 1, "comment": "再次确认 LanceDB 选型,生产跑了 3 个月稳定", "created_at": "2026-05-01T09:14:22Z"},
      {"review_id": "review_01jzs7mp", "session_id": "sess_def456", "indexes": "5,8", "score": -1, "comment": "原以为 mmap NFS 没事,生产撞了 inode lock 的坑", "created_at": "2026-04-22T18:03:11Z"}
    ],
    "stats": {
      "review_up": 1,
      "review_down": 1,
      "review_neutral": 1,
      "review_count": 3,
      "read_count": 8,
      "recall_count": 4
    },
    "created_at": "2026-04-10T14:30:00Z"
  }
}
```

`card` 对象的字段定义见 [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)。

### 响应:session

```json
{
  "type": "session",
  "read_at": "2026-05-18T14:32:05Z",
  "session": {
    "session_id": "sess_187c6576",
    "source": "claude-code",
    "created_at": "2026-04-10T14:30:00Z",
    "metadata": {"cwd": "/home/user/myapp"},
    "rounds": [
      {
        "index": 1,
        "round_id": "r001",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}]
      }
    ]
  }
}
```

`session` 对象的字段定义见 [`../../structure/v3/session.md`](../../structure/v3/session.md)。

### 返回体规则

- 顶层 `type` 标明本次读出的是 card 还是 session(`"card"` / `"session"`)。
- 顶层 `read_at` 是服务端处理时间(ISO 8601 UTC)。
- card 响应的 `reviews` 按 `created_at` 倒序排列;`stats` 是当前快照。
- session 响应**没有** `tags` / `links` 字段 —— v3 无这两个概念。
- Session 的 rounds 一次性全部返回,不支持窗口参数(过长 session 在 search 侧用更精准的 `where` 缩小)。

### 副作用

- **read card** → `card.stats.read_count += 1`(原子 upsert,无锁竞争)。写一条 `read_at` 事件到 `cards/{...}/{card_id}/events.jsonl`(detail 含 `read_at` 时间戳)。
- **read session** → **完全只读**,不更新任何 stats,不写任何事件。session 不参与 card 论坛动力学。
- 不刷新任何 TTL —— v3 无 TTL 概念。

### 错误

| 情况 | 状态 |
|---|---|
| `id` 缺失 / 非字符串 | 400, `id required` |
| `id` 前缀不是 `card_` / `sess_` | 400, `invalid id prefix` |
| id 合法但对象不存在 | 404 |

### 跟 v2 的差异

| | v2 (`/v2/view`) | v3 (`/v3/read`) |
|---|---|---|
| 路径 | `/v2/view` | `/v3/read` |
| card 字段 | `summary` + `rounds` + `ttl` + `links` | `insight` + `source_cards` + `rounds` + `reviews` + `stats` |
| session 字段 | `tags` + `links` 都有 | 都没 |
| card 副作用 | 刷 card TTL + 活跃 link TTL | `read_count += 1`,无 TTL |
