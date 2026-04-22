# view

按 search 返回的 `result_id` 读取具体对象——card 和 session 共用这一个入口，按 result_id 前缀（`.c<N>` / `.s<N>`）自动分发。服务端同时记录一条 click。

```bash
memory-talk view <result_id>
```

例：

```bash
memory-talk view sch_01K7XABC....c1        # 读取 card
memory-talk view sch_01K7XABC....s1        # 读取 session
```

参数：
- `<result_id>` 必须是 `.c<N>` 或 `.s<N>` 形态。其它（例如 `.l<N>` 这种只在 view 响应里出现的子 result_id）同样接受——服务端按对应的 `target_type` 分发。
- 过期的 result_id（超出 `settings.search.result_ttl`）返回 `expired`。
- 未知 result_id 返回 404。

## 输出

响应体用 `type` 字段标明本次 view 出的是 card 还是 session，对应的主体内容放在同名字段下。

### card

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
    {
      "target_result_id": "sch_01K7XABC....c1.l1",
      "target_type": "session",
      "comment": null,
      "ttl": 0
    },
    {
      "target_result_id": "sch_01K7XABC....c1.l2",
      "target_type": "card",
      "comment": "选型后果——NFS 上踩的坑",
      "ttl": 1814400
    },
    {
      "target_result_id": "sch_01K7XABC....c1.l3",
      "target_type": "card",
      "comment": "早期失败的 ChromaDB 方案",
      "ttl": -86400
    }
  ]
}
```

### session

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
        "round_id": "r001",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}]
      },
      {
        "round_id": "r002",
        "speaker": "assistant",
        "role": "assistant",
        "content": [{"type": "text", "text": "推荐 LanceDB，零依赖嵌入式"}]
      }
    ]
  },
  "links": [
    {
      "target_result_id": "sch_01K7XABC....s1.l1",
      "target_type": "card",
      "comment": "从此对话提取",
      "ttl": 1209600
    }
  ]
}
```

## 要点

- 响应体不出现裸 `card_id` / `session_id` / `link_id`。
- `links[].target_result_id` 形如 `{parent_result_id}.l<N>`——是服务端在本次 view 时为每条出链现生的子 result_id，可直接再喂给 `view` 继续追下去，不需要关心目标是 card 还是 session。
- `links[].ttl` 三种取值：
  - `= 0`：默认 link（card 写入时自动生成的 card→session 关联）。随 card 一起存在，不独立计时，view 不续命。
  - `> 0`：活跃的用户 link。view 时按 `ttl.link.factor` 隐式续命。
  - `< 0`：已过期的用户 link。**view 仍会返回**（方便看"它当初指向过什么"），但不会续命、也不会出现在 search 的 link 列表里。
- 本次读取会**隐式刷新被读对象自己的 TTL 以及所有活跃用户 link 的 TTL**（`ttl > 0` 的那些）——默认 link（`ttl = 0`）和已过期 link（`ttl < 0`）都不参与续命。v1 需要 `--link-id` 显式传参才能刷新某条 link，v2 不再需要。
- Card 响应体里 **v1 遗留的顶层 `session_id`** 字段在 v2 里不暴露。要追到该 card 来源的 session，看 `card.rounds[].session_id`（这是每条 round 自带的溯源字段），或 `links` 里 `target_type: "session"` 的条目。
- Session 的 rounds 一次性全部返回，不支持窗口参数。若 session 过长不适合整体读取，在 search 侧用更精准的 `query` / `--where` 缩小命中。

Round / ContentBlock 结构见 [session.md](../../structure/v2/session.md)，Card 结构见 [talk-card.md](../../structure/v2/talk-card.md)。

## 追踪语义

每次 view 都会在服务端写一条 click（search_id, rank, result_id, read_at）。结合 `search_log` 可以分析"这次 search 引导出哪些读取、哪些引用、哪些新建的 card"。
