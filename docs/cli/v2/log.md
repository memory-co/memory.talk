# log

查一个 card 或 session 的**全生命周期**——什么时候被创建 / 导入、什么时候被打 tag、什么时候被 link、什么时候有 card 从它身上提取、什么时候 sync 追加了新 round……按时间顺序排列。

```bash
memory-talk log <id> [--json]
```

`<id>` 必须是 `card_<...>` 或 `sess_<...>`——服务端按前缀自动判型。

`log` 本身是纯只读的元数据查询，不刷新 TTL、不产生事件——事件流**只记录真实的写行为**。读（search、view、log 自身）不入 log；TTL 归零是被动结果，也不入 log。幂等 no-op（如 `tag add` 时该 tag 已存在）**不算写行为**，不产生事件。

## 输出（Text，默认）

事件按时间升序排列（最老的在前），方便当成"故事线"从上往下读。

### session

```
sess_187c6576 (7 events)

  2026-04-10T14:30:00Z  imported           source=claude-code · round_count=20
  2026-04-11T09:00:00Z  rounds_appended    indexes 21-28 (+8)
  2026-04-15T11:20:00Z  tag_added          decision
  2026-04-15T11:20:00Z  tag_added          project:memory-talk
  2026-04-16T10:30:00Z  card_extracted     card_01jz8k2m · indexes=11-15
  2026-04-17T14:02:33Z  linked             ←incoming card_01jzp3nq (后续踩了 NFS 的坑) · ttl=14d
  2026-04-19T08:00:00Z  tag_removed        decision
```

### card

```
card_01jz8k2m (2 events)

  2026-04-16T10:30:00Z  created            选定 LanceDB 做向量存储 · rounds=sess_abc123/11-15 · 1 default_link · ttl=30d · from sch_01K7XABC
  2026-04-19T09:05:11Z  linked             →outgoing card_01jzp3nq (替代方案 ChromaDB 的选型讨论) · ttl=14d
```

约定：
- 三列对齐：`<UTC ISO 时间>  <kind>  <detail 摘要>`。kind 列宽 18 字符以容纳最长的 `rounds_overwrite_skipped`。
- `linked` 用 `←incoming` / `→outgoing` 标方向。
- 摘要里的字段次序固定：先主语（id / 内容），再修饰（comment / ttl / source 等）。
- 完整 detail 看 `--json`。

## 输出（`--json`）

事件按时间升序排列（最老的在前）。

### session

```json
{
  "type": "session",
  "session_id": "sess_187c6576",
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
        "card_id": "card_01jz8k2m",
        "indexes": "11-15",
        "default_link_id": "link_01jzq7rm"
      }
    },
    {
      "at": "2026-04-17T14:02:33Z",
      "kind": "linked",
      "detail": {
        "direction": "incoming",
        "link_id": "link_01jzq8sn",
        "peer_id": "card_01jzp3nq",
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
  "type": "card",
  "card_id": "card_01jz8k2m",
  "events": [
    {
      "at": "2026-04-16T10:30:00Z",
      "kind": "created",
      "detail": {
        "summary": "选定 LanceDB 做向量存储",
        "rounds": [{"session_id": "sess_abc123", "indexes": "11-15"}],
        "default_links": [{"link_id": "link_01jzq7rm", "target_id": "sess_abc123"}],
        "ttl_initial": 2592000,
        "from_search_id": "sch_01K7XABC..."
      }
    },
    {
      "at": "2026-04-19T09:05:11Z",
      "kind": "linked",
      "detail": {
        "direction": "outgoing",
        "link_id": "link_01jzq9tm",
        "peer_id": "card_01jzp3nq",
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
| `card_extracted` | 有 card 写入时引用了本 session 的 round | `card_id`, `indexes`, `default_link_id` |
| `linked` | 用户 link 被写入，两端之一是本 session | `direction`（`incoming` / `outgoing`）, `link_id`, `peer_id`, `peer_type`, `comment`, `ttl_initial` |

### card

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `created` | card 写入 | `summary`, `rounds`（写入 input：`[{session_id, indexes}, ...]`）, `default_links`（`[{link_id, target_id}, ...]`）, `ttl_initial`, `from_search_id`（可选：若调用方在 card 请求里关联了 search_id，则回填） |
| `linked` | 用户 link 被写入，两端之一是本 card | `direction`, `link_id`, `peer_id`, `peer_type`, `comment`, `ttl_initial` |

说明：

- **tag 事件按 tag 粒度**：`tag add foo bar` 若两个都是新 tag 会产生两条 `tag_added` 事件；其中一个已存在（幂等跳过）就只产生一条。
- **`card_extracted` 按 session 合并**：card 输入里同一 `session_id` 出现多次的情况（`[{session_id:"sess_abc", indexes:"11-15"}, {session_id:"sess_abc", indexes:"20,22"}]`），**合并为一条 `card_extracted`**，detail 里 `indexes` 字段是合并并按升序归一后的字符串（`"11-15,20,22"`）。
- **`linked` 两端都打事件**：同一条用户 link，两端对象的 log 里各记一条 `linked`，用 `direction` 区分。
- **`from_search_id`**：写 card / 建 link 时，调用方可以选择性地带上当时在用的 `search_id`（来自某次 search 的响应），服务端落事件时回填。这样在 log 里能看到"这张 card 是因为某次 search 才有动因"——不是强制，只是方便 tool-use 对照。

## 错误

- 非法前缀：text 模式 `error: invalid id` 到 stderr，exit 1；JSON 模式 `{"error": "invalid id ..."}`。
- 未知 / 不存在 id：404，错误同上但消息为 `not found`。
