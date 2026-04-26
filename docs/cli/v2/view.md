# view

按带前缀的 id 读取 card 或 session——**服务端按 id 前缀自动判型**：`card_*` 走 card 读取，`sess_*` 走 session 读取，其它前缀 400。

```bash
memory-talk view <id> [--json]
```

例：

```bash
memory-talk view card_01jz8k2m            # text 默认
memory-talk view sess_187c6576 --json
```

参数：
- `<id>` 必须是 `card_<...>` 或 `sess_<...>`。非法前缀或不存在的 id 返回错误。
- `--json` 输出 JSON。

## 输出（Text，默认）

### card

```
card_01jz8k2m  ttl=28d  read_at=2026-04-20T14:32:05Z
选定 LanceDB 做向量存储

rounds (2):
  [sess_abc123#11 human]     ChromaDB vs LanceDB?
  [sess_abc123#12 assistant] 推荐 LanceDB 零依赖

links (3):
  → sess_abc123    (session)
  → card_01jzp3nq  (card · 选型后果——NFS 上踩的坑) · ttl=21d
  → card_01jzold99 (card · 早期失败的 ChromaDB 方案) · expired
```

### session

```
sess_187c6576  source=claude-code  created=2026-04-10  read_at=2026-04-20T14:32:05Z
tags: decision, project:memory-talk
metadata: project=/home/user/myapp

rounds (2):
  [#1 human]     ChromaDB vs LanceDB?
  [#2 assistant] 推荐 LanceDB，零依赖嵌入式

links (1):
  → card_01jz8k2m (card · 从此对话提取) · ttl=14d
```

约定：
- 单条 round 文本太长时,在 80 列宽处截断附 `…`,完整内容看 `--json`。
- 多 ContentBlock 的 round（含 thinking 等非 text 块）用 `+ <type>` 标注:`[#3 assistant +thinking +tool_use] ...`。
- `links` 里 `(comment)` 仅在有 comment 时显示。`ttl=0` 是默认 link,展示为不带 ttl 字段(因为它跟随对象生死)。`ttl > 0` 是活跃用户 link。`expired` 即 `ttl < 0`。

## 输出（`--json`）

响应体用 `type` 字段标明本次 view 出的是 card 还是 session，对应主体内容放在同名字段下。

### card

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

### session

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
      },
      {
        "index": 2,
        "round_id": "r002",
        "speaker": "assistant",
        "role": "assistant",
        "content": [{"type": "text", "text": "推荐 LanceDB，零依赖嵌入式"}]
      }
    ]
  },
  "links": [
    {"link_id": "link_01jzq7rm", "target_id": "card_01jz8k2m", "target_type": "card", "comment": "从此对话提取", "ttl": 1209600}
  ]
}
```

## 要点

- 响应直接暴露**带前缀的裸 id**（`card_id` / `session_id` / `link_id` / `target_id`），拿到就能喂给下一次 `view` / `log` / `link create`。
- `links[].ttl` 三种语义：
  - `= 0`：默认 link（card 写入时自动生成的 card→session）。随 card 一起存在，不独立计时，**不被续命**。
  - `> 0`：活跃的用户 link。view 时按 `ttl.link.factor` **隐式续命**。
  - `< 0`：已过期的用户 link。**仍会返回**（方便看"当初指向过什么"），**不续命**，也不会出现在 `search` 的 link 列表里。
- 本次读取会**隐式刷新被读对象自己的 TTL 以及所有活跃用户 link 的 TTL**（`ttl > 0` 的那些）——默认 link 和已过期 link 都不参与续命。
- Session 的 rounds 一次性全部返回，不支持窗口参数。若 session 过长，在 search 侧用更精准的 `query` / `--where` 缩小命中。

Round / ContentBlock 结构见 [session.md](../../structure/v2/session.md)，Card 结构见 [talk-card.md](../../structure/v2/talk-card.md)。

## 副作用

- view card 时，**刷新 card 自身的 TTL**（按 `ttl.card.factor`）。view session 时不刷新——session 本身没有 TTL，是永久对象。
- 两种场景都**隐式刷新活跃用户 link** 的 TTL（`ttl > 0`，按 `ttl.link.factor`）。默认 link（`ttl=0`）和已过期 link（`ttl<0`）不参与。
