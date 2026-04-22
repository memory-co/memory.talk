# View API

## POST /v2/view

按带前缀的 id 读取 card 或 session——服务端**按 id 前缀自动判型**：`card_*` 走 card 读取，`sess_*` 走 session 读取，其它前缀 400。

请求体：

```json
{"id": "card_01jz8k2m"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | `card_<ULID>` 或 `sess_<ULID>` |

## 响应：card

```json
{
  "type": "card",
  "read_at": "2026-04-20T14:32:05Z",
  "card": {
    "card_id": "card_01jz8k2m",
    "summary": "选定 LanceDB 做向量存储",
    "rounds": [
      {"role": "human", "text": "ChromaDB vs LanceDB?", "session_id": "sess_abc123", "index": 11},
      {"role": "assistant", "text": "推荐 LanceDB 零依赖", "session_id": "sess_abc123", "index": 12}
    ],
    "created_at": "2026-04-10T14:30:00Z",
    "ttl": 2419200
  },
  "links": [
    {"link_id": "link_01jzq7rm", "target_id": "sess_abc123", "target_type": "session", "comment": null, "ttl": 0},
    {"link_id": "link_01jzq8sn", "target_id": "card_01jzp3nq", "target_type": "card", "comment": "选型后果——NFS 上踩的坑", "ttl": 1814400},
    {"link_id": "link_01jzq9tm", "target_id": "card_01jzold99", "target_type": "card", "comment": "早期失败的 ChromaDB 方案", "ttl": -86400}
  ]
}
```

## 响应：session

```json
{
  "type": "session",
  "read_at": "2026-04-20T14:32:05Z",
  "session": {
    "session_id": "sess_187c6576",
    "source": "claude-code",
    "created_at": "2026-04-10T14:30:00Z",
    "tags": ["decision", "project:memory-talk"],
    "metadata": {"project": "/home/user/myapp"},
    "rounds": [
      {
        "index": 1,
        "round_id": "r001",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}]
      }
    ]
  },
  "links": [
    {"link_id": "link_01jzq7rm", "target_id": "card_01jz8k2m", "target_type": "card", "comment": "从此对话提取", "ttl": 1209600}
  ]
}
```

## 返回体规则

- 直接暴露**带前缀的裸 id**（`card_id` / `session_id` / `link_id` / `target_id`），可直接再调其它端点。
- `links[].ttl` 三种语义：
  - `= 0`：默认 link（card 写入时自动生成的 card→session）。随 card 一起存在，不独立计时，**不被续命**。
  - `> 0`：活跃的用户 link。view 时按 `ttl.link.factor` **隐式续命**。
  - `< 0`：已过期的用户 link。**仍会返回**（方便看"当初指向过什么"），**不续命**，也不会出现在 `/v2/search` 的 link 列表里。
- Session 的 rounds 一次性全部返回，不支持窗口参数。

## 副作用

- view card 时**刷新 card 自身 TTL**（按 `ttl.card.factor`）。view session 时不刷新——session 没有 TTL，是永久对象。
- 两种场景都**隐式刷新活跃用户 link**（`ttl > 0`，按 `ttl.link.factor`）。默认 link 和已过期 link 不参与。
- **不写 view.jsonl**——v2 不追踪 view 调用（AI tool-use 对话本身是完整的 view 记录）。

## 错误

| 情况 | 状态 |
|------|------|
| `id` 前缀非 `card_` / `sess_` | 400，`invalid id prefix` |
| id 合法但对象不存在 | 404 |
