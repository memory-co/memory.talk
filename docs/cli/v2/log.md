# log

查一个 card 或 session 的**全生命周期**——什么时候被创建 / 导入、什么时候被打 tag、什么时候被 link、什么时候有 card 从它身上提取、什么时候 sync 追加了新 round……按时间顺序排列。

```bash
memory-talk log <result_id>
```

参数与 `view` 同源：必须是一个 result_id（`.c<N>` / `.s<N>` / `.l<N>`）。v2 的引用路径统一经过 search，log 也不例外——你得先把对象从 search 里捞出来，再查它的历史。

`log` 本身是纯只读的元数据查询，不刷新 TTL、不产生事件——事件流**只记录真实的写行为**。读（search、view、log 自身）不入 log；TTL 归零是时间被动推进的结果，也不入 log。幂等 no-op（如 `tag add` 时该 tag 已存在）**不算写行为**，不产生事件。

## ID 处理

log 响应**不暴露裸 `card_id` / `session_id` / `link_id`**——事件里凡是需要引用另一个对象的地方，都现生一个子 result_id `{parent_result_id}.e<N>`（`e` = event reference），可直接喂给 `view` / `link create` / `log` 继续追。

`.e<N>` 语义和 view 返回的 `.l<N>` 一样：一次响应内有效，带 TTL（同 `settings.search.result_ttl`）。类型（card / session / link）由 `detail` 里同级的 `*_type` 字段标明。

## 输出

事件按时间升序排列（最老的在前），方便当成"故事线"从上往下读。

### session

```json
{
  "result_id": "sch_01K7XABC....s1",
  "type": "session",
  "events": [
    {
      "at": "2026-04-10T14:30:00Z",
      "kind": "imported",
      "detail": {"source": "claude-code", "round_count": 20}
    },
    {
      "at": "2026-04-11T09:00:00Z",
      "kind": "rounds_appended",
      "detail": {"from_index": 21, "to_index": 28, "added_count": 8}
    },
    {
      "at": "2026-04-15T11:20:00Z",
      "kind": "tag_added",
      "detail": {"tag": "decision"}
    },
    {
      "at": "2026-04-15T11:20:00Z",
      "kind": "tag_added",
      "detail": {"tag": "project:memory-talk"}
    },
    {
      "at": "2026-04-16T10:30:00Z",
      "kind": "card_extracted",
      "detail": {
        "card": "sch_01K7XABC....s1.e1",
        "card_type": "card",
        "indexes": "11-15"
      }
    },
    {
      "at": "2026-04-17T14:02:33Z",
      "kind": "linked",
      "detail": {
        "direction": "incoming",
        "peer": "sch_01K7XABC....s1.e2",
        "peer_type": "card",
        "comment": "后续踩了 NFS 的坑",
        "ttl_initial": 1209600
      }
    },
    {
      "at": "2026-04-19T08:00:00Z",
      "kind": "tag_removed",
      "detail": {"tag": "decision"}
    }
  ]
}
```

### card

```json
{
  "result_id": "sch_01K7XABC....c1",
  "type": "card",
  "events": [
    {
      "at": "2026-04-16T10:30:00Z",
      "kind": "created",
      "detail": {
        "summary": "选定 LanceDB 做向量存储",
        "sources": [
          {"session": "sch_01K7XABC....c1.e1", "session_type": "session", "indexes": "11-15"}
        ],
        "default_links_count": 1,
        "ttl_initial": 2592000
      }
    },
    {
      "at": "2026-04-19T09:05:11Z",
      "kind": "linked",
      "detail": {
        "direction": "outgoing",
        "peer": "sch_01K7XABC....c1.e2",
        "peer_type": "card",
        "comment": "替代方案 ChromaDB 的选型讨论",
        "ttl_initial": 1209600
      }
    }
  ]
}
```

## 事件表

### session

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `imported` | 首次 `sync` 导入 | `source`, `round_count` |
| `rounds_appended` | `sync` 再次扫到本 session、且文件里的 round 数增长（仅追加部分） | `from_index`, `to_index`, `added_count` |
| `rounds_overwrite_skipped` | `sync` 检测到已有 round 内容被平台覆写，整次 sync 跳过了这些 round（见 [sync.md](sync.md)） | `indexes`（被跳过的 round `index` 列表） |
| `tag_added` | `tag add` 实际加上了一个之前没有的 tag | `tag` |
| `tag_removed` | `tag remove` 实际移除了一个存在的 tag | `tag` |
| `card_extracted` | 有 card 写入时引用了本 session 的 round | `card`（`.e<N>`）, `card_type`（恒为 `card`）, `indexes` |
| `linked` | 用户 link 被写入，两端之一是本 session | `direction`（`incoming` / `outgoing`）, `peer`（`.e<N>`）, `peer_type`, `comment`, `ttl_initial` |

### card

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `created` | card 写入 | `summary`, `sources`（`[{session, session_type, indexes}, ...]`，每项 `session` 是 `.e<N>`）, `default_links_count`, `ttl_initial` |
| `linked` | 用户 link 被写入，两端之一是本 card | `direction`, `peer`（`.e<N>`）, `peer_type`, `comment`, `ttl_initial` |

说明：

- **tag 事件按 tag 粒度**：`tag add foo bar` 若两个都是新 tag 会产生两条 `tag_added` 事件；其中一个已存在（幂等跳过）就只产生一条。`tag remove` 同理。
- **`card_extracted` 按 session 合并**：card 输入里同一 `session_id` 出现多次的情况（`[{session_id:"abc", indexes:"11-15"}, {session_id:"abc", indexes:"20,22"}]`），**合并为一条 `card_extracted`**，detail 里 `indexes` 字段是合并并按升序归一后的字符串（`"11-15,20,22"`）。
- **`default_links_count`**：card `created` 事件只给个计数，不逐条列默认 link（它们可以通过 view 本 card 的 `links` 字段拿到，`ttl=0` 的就是）。
- **`linked` 两端都打事件**：同一条用户 link，两端对象的 log 里各记一条 `linked`，用 `direction` 区分。

## 错误

- 过期 result_id：`expired`
- 未知 result_id：404
- 传了 `.l<N>` 时按 link 指向的对端解析后再查（和 view 一致）
