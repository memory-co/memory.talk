# Log API

## POST /v2/log

查一个 card 或 session 的全生命周期事件流——创建 / 导入、tag 变更、被 link、被 card 提取、sync 追加 round 等。**纯只读**，不写 click、不刷 TTL、不产生事件。

请求体：

```json
{"result_id": "sch_01K7XABC....s1"}
```

## 响应：session

```json
{
  "result_id": "sch_01K7XABC....s1",
  "type": "session",
  "events": [
    {"at": "2026-04-10T14:30:00Z", "kind": "imported", "detail": {"source": "claude-code", "round_count": 20}},
    {"at": "2026-04-11T09:00:00Z", "kind": "rounds_appended", "detail": {"from_index": 21, "to_index": 28, "added_count": 8}},
    {"at": "2026-04-15T11:20:00Z", "kind": "tag_added", "detail": {"tag": "decision"}},
    {"at": "2026-04-15T11:20:00Z", "kind": "tag_added", "detail": {"tag": "project:memory-talk"}},
    {"at": "2026-04-16T10:30:00Z", "kind": "card_extracted", "detail": {"card": "sch_01K7XABC....s1.e1", "card_type": "card", "indexes": "11-15"}},
    {"at": "2026-04-17T14:02:33Z", "kind": "linked", "detail": {"direction": "incoming", "peer": "sch_01K7XABC....s1.e2", "peer_type": "card", "comment": "后续踩了 NFS 的坑", "ttl_initial": 1209600}},
    {"at": "2026-04-19T08:00:00Z", "kind": "tag_removed", "detail": {"tag": "decision"}}
  ]
}
```

## 响应：card

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
        "sources": [{"session": "sch_01K7XABC....c1.e1", "session_type": "session", "indexes": "11-15"}],
        "default_links_count": 1,
        "ttl_initial": 2592000
      }
    },
    {
      "at": "2026-04-19T09:05:11Z",
      "kind": "linked",
      "detail": {"direction": "outgoing", "peer": "sch_01K7XABC....c1.e2", "peer_type": "card", "comment": "替代方案 ChromaDB", "ttl_initial": 1209600}
    }
  ]
}
```

## 返回体规则

- 事件按 `at` **升序**（老→新）。
- **不暴露裸 `card_id` / `session_id` / `link_id`**——事件里凡是引用其它对象的地方都现生一个子 result_id `{parent_result_id}.e<N>`，可直接喂给 `/v2/view` / `/v2/links` / `/v2/log` 继续追。`.e<N>` TTL 和 search result_id 一致。
- 类型（card / session / link）由 `detail` 里同级的 `*_type` 字段标明。

## 事件 kind 表

### session

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `imported` | 首次 `POST /v2/sessions` | `source`, `round_count` |
| `rounds_appended` | 同 session 再次 ingest、round 数增长（仅追加部分） | `from_index`, `to_index`, `added_count` |
| `rounds_overwrite_skipped` | ingest 检测到已有 round 被平台覆写、被跳过 | `indexes` |
| `tag_added` | `POST /v2/tags/add` 实际加上了一个之前没有的 tag | `tag` |
| `tag_removed` | `POST /v2/tags/remove` 实际移除了一个存在的 tag | `tag` |
| `card_extracted` | 有 card 写入时引用了本 session 的 round | `card`（`.e<N>`）, `card_type`, `indexes` |
| `linked` | 用户 link 被写入，两端之一是本 session | `direction`, `peer`（`.e<N>`）, `peer_type`, `comment`, `ttl_initial` |

### card

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `created` | `POST /v2/cards` | `summary`, `sources`（`[{session, session_type, indexes}, ...]`）, `default_links_count`, `ttl_initial` |
| `linked` | 用户 link 被写入，两端之一是本 card | `direction`, `peer`（`.e<N>`）, `peer_type`, `comment`, `ttl_initial` |

说明：

- **tag 事件按 tag 粒度**。一次 `POST /v2/tags/add` 传入两个新 tag → 两条事件。幂等 no-op（tag 已存在）**不记事件**。
- **`card_extracted` 按 session 合并**。card 输入里同一 session 多次出现（例如 `[{session_id:"abc", indexes:"11-15"}, {session_id:"abc", indexes:"20,22"}]`），合并成一条事件，`indexes` = `"11-15,20,22"`。
- **`default_links_count`** 只给计数，不逐条列默认 link。要看具体可调 `/v2/view`，`links[].ttl = 0` 的就是。
- **`linked` 两端都打事件**，用 `direction: incoming|outgoing` 区分。

## 错误

同 [view.md](view.md) 的错误码。log 不对 `.l<N>` 做自动拆解——传入 `.l<N>` 时按 link 指向的对端对象解析后返回那个对象的 log。
