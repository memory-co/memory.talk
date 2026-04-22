# Log API

## POST /v2/log

查一个 card 或 session 的全生命周期事件流——创建 / 导入、tag 变更、被 link、被 card 提取、sync 追加 round 等。**纯只读**，不写 click、不刷 TTL、不产生事件。

请求体：

```json
{"id": "sess_187c6576"}
```

服务端按 `id` 前缀（`card_` / `sess_`）自动判型并返回对应对象的事件流。

## 响应：session

```json
{
  "type": "session",
  "session_id": "sess_187c6576",
  "events": [
    {"at": "2026-04-10T14:30:00Z", "kind": "imported", "detail": {"source": "claude-code", "round_count": 20}},
    {"at": "2026-04-11T09:00:00Z", "kind": "rounds_appended", "detail": {"from_index": 21, "to_index": 28, "added_count": 8}},
    {"at": "2026-04-15T11:20:00Z", "kind": "tag_added", "detail": {"tag": "decision"}},
    {"at": "2026-04-15T11:20:00Z", "kind": "tag_added", "detail": {"tag": "project:memory-talk"}},
    {"at": "2026-04-16T10:30:00Z", "kind": "card_extracted", "detail": {"card_id": "card_01jz8k2m", "indexes": "11-15", "default_link_id": "link_01jzq7rm"}},
    {"at": "2026-04-17T14:02:33Z", "kind": "linked", "detail": {"direction": "incoming", "link_id": "link_01jzq8sn", "peer_id": "card_01jzp3nq", "peer_type": "card", "comment": "后续踩了 NFS 的坑", "ttl_initial": 1209600}}
  ]
}
```

## 响应：card

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
      "detail": {"direction": "outgoing", "link_id": "link_01jzq9tm", "peer_id": "card_01jzp3nq", "peer_type": "card", "comment": "替代方案 ChromaDB", "ttl_initial": 1209600}
    }
  ]
}
```

## 返回体规则

- 事件按 `at` **升序**（老→新）。
- 事件里引用其它对象的地方直接暴露**带前缀的裸 id**（`card_id` / `peer_id` / `link_id` / `default_link_id` 等），可直接喂给 `/v2/view`。

## 事件 kind 表

### session

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `imported` | 首次 `POST /v2/sessions` | `source`, `round_count` |
| `rounds_appended` | 同 session 再次 ingest、round 数增长（仅追加部分） | `from_index`, `to_index`, `added_count` |
| `rounds_overwrite_skipped` | ingest 检测到已有 round 被平台覆写、被跳过 | `indexes` |
| `tag_added` | `POST /v2/tags/add` 实际加上了一个之前没有的 tag | `tag` |
| `tag_removed` | `POST /v2/tags/remove` 实际移除了一个存在的 tag | `tag` |
| `card_extracted` | 有 card 写入时引用了本 session 的 round | `card_id`, `indexes`, `default_link_id` |
| `linked` | 用户 link 被写入，两端之一是本 session | `direction`, `link_id`, `peer_id`, `peer_type`, `comment`, `ttl_initial` |

### card

| kind | 触发 | detail 关键字段 |
|------|------|----------------|
| `created` | `POST /v2/cards` | `summary`, `rounds`（`[{session_id, indexes}, ...]`）, `default_links`（`[{link_id, target_id}, ...]`）, `ttl_initial`, `from_search_id`（可选） |
| `linked` | 用户 link 被写入，两端之一是本 card | `direction`, `link_id`, `peer_id`, `peer_type`, `comment`, `ttl_initial` |

说明：

- **tag 事件按 tag 粒度**。一次 `POST /v2/tags/add` 传入两个新 tag → 两条事件。幂等 no-op（tag 已存在）**不记事件**。
- **`card_extracted` 按 session 合并**。card 输入里同一 session 多次出现（例如 `[{session_id:"sess_abc", indexes:"11-15"}, {session_id:"sess_abc", indexes:"20,22"}]`），合并成一条事件，`indexes` = `"11-15,20,22"`。
- **`linked` 两端都打事件**，用 `direction: incoming|outgoing` 区分。
- **`from_search_id`**（可选）：`POST /v2/cards` 请求里可以带一个来自上一次 search 的 `search_id`，服务端落 `created` 事件时回填。方便日后在 log 里追到"这张 card 是因为哪次 search 才有的动因"。

## 错误

| 情况 | 状态 |
|------|------|
| `id` 前缀非 `card_` / `sess_` | 400，`invalid id prefix` |
| id 合法但对象不存在 | 404 |
