# View API

## POST /v2/view

按 search 返回的 `result_id` 读取具体对象——card 和 session 共用这一个入口，按 result_id 前缀（`.c<N>` / `.s<N>` / `.l<N>`）自动分发。

请求体：

```json
{"result_id": "sch_01K7XABC....c1"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `result_id` | 是 | `.c<N>` / `.s<N>`，或 view / log 响应里现生的 `.l<N>` / `.e<N>` |

## 响应：card

```json
{
  "result_id": "sch_01K7XABC....c1",
  "type": "card",
  "read_at": "2026-04-20T14:32:05Z",
  "card": {
    "summary": "选定 LanceDB 做向量存储",
    "rounds": [
      {"role": "human", "text": "ChromaDB vs LanceDB?", "session_id": "abc123", "index": 11},
      {"role": "assistant", "text": "推荐 LanceDB 零依赖", "session_id": "abc123", "index": 12}
    ],
    "created_at": "2026-04-10T14:30:00Z",
    "ttl": 2419200
  },
  "links": [
    {"target_result_id": "sch_01K7XABC....c1.l1", "target_type": "session", "comment": null, "ttl": 0},
    {"target_result_id": "sch_01K7XABC....c1.l2", "target_type": "card", "comment": "选型后果——NFS 上踩的坑", "ttl": 1814400},
    {"target_result_id": "sch_01K7XABC....c1.l3", "target_type": "card", "comment": "早期失败的 ChromaDB 方案", "ttl": -86400}
  ]
}
```

## 响应：session

```json
{
  "result_id": "sch_01K7XABC....s1",
  "type": "session",
  "read_at": "2026-04-20T14:32:05Z",
  "session": {
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
    {"target_result_id": "sch_01K7XABC....s1.l1", "target_type": "card", "comment": "从此对话提取", "ttl": 0}
  ]
}
```

## 返回体规则

- 不暴露裸 `card_id` / `session_id` / `link_id`。要追到 card 来源的 session，用 `card.rounds[].session_id` + `index`，或 `links` 里 `target_type: "session"` 的条目。
- `links[].target_result_id` 形如 `{parent_result_id}.l<N>`——本次 view 现生的子 result_id，可直接再调 `/v2/view` 继续追。
- `links[].ttl` 三种语义：
  - `= 0`：默认 link（card 写入时自动生成的 card→session）。随 card 一起存在，不独立计时，**不被续命**。
  - `> 0`：活跃的用户 link。view 时按 `ttl.link.factor` **隐式续命**。
  - `< 0`：已过期的用户 link。**仍会返回**（方便看"当初指向过什么"），**不续命**，也不会出现在 `/v2/search` 的 link 列表里。
- Session 的 rounds 一次性全部返回，不支持窗口参数。若 session 过长，在 search 侧用更精准的 `query` / `where` 缩小命中。

## 副作用

- 向 `logs/view.jsonl` 追加一条 click（`search_id`, `rank`, `result_id`, `read_at`），同步写入 SQLite 的 view click 表。
- 隐式刷新被读对象自己的 TTL（用 `ttl.card.factor` 或 session 对应项）。
- 隐式刷新所有**活跃用户 link**（`ttl > 0`）的 TTL。默认 link 和已过期 link 都不参与。

## 错误

| 情况 | 状态 |
|------|------|
| `result_id` 格式非法（不是 `.c` / `.s` / `.l` 开头的合法形态） | 400 |
| `result_id` 已过期 | 410，`expired` |
| `result_id` 未知 | 404 |
| `.l<N>` 指向的 link 已过期 | 410，`expired`（断链不追） |
