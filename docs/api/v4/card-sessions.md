# Card-Sessions API

**card↔session 出处**关系:哪个 session(的哪几条旁白 round)**启发 / 生出**了这张卡或某个答案。和 [card↔card 的 links](card-links.md) 平行,都嵌在卡下(`/v4/cards/{card_id}/...`)。支持多 session。

CLI 一般不直接调——出处由**旁白 / 标注机制**自动写入(也可在 [`POST /v4/cards/{card_id}/positions`](cards.md#post-v4cardscard_idpositions) 带 `source`、或 [session-mark](../../works/v4/session-mark.md))。本页端点用于显式记录和反查。字段语义详见 [`../../structure/v4/card-session.md`](../../structure/v4/card-session.md)。

> SQLite 表名仍是 `card_sessions`(只是 API 路径嵌到卡下)。canonical 是旁白的 `questions[]`(file),这张表是它的派生 join 索引。

---

## POST /v4/cards/{card_id}/sessions

给 `{card_id}` 显式记一条出处。

### 请求体

```json
{
  "session_id": "sess_abc123",
  "position_id": "pos_01jzp3nq",
  "indexes": "11-15"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 哪个 session,`sess_<...>`。**扁平列、可 join、无 FK** |
| `position_id` | 否 | 启发了哪个答案。空 / `""` = 关联到**问题 / 卡本身**(不指向具体答案) |
| `indexes` | 否 | 那个 session 里**标了 `#问题` 的旁白 round**(同 `reviews.indexes` 语法),默认 `[]` |

(卡 = 路径里的 `{card_id}`。)

### 主键 / 多值

主键 `(card_id, session_id, position_id)`:同一卡可挂多个 session;同一 session 也可启发同卡的多个答案。重复 → 幂等。

### 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m", "session_id": "sess_abc123", "position_id": "pos_01jzp3nq"}
```

### 副作用

- 校验路径 `card_id` 存在、`session_id` 前缀合法 → 失败不落库。
- 写一行 `card_sessions`。
- **不加 FOREIGN KEY**(容忍悬挂 `session_id`——SQLite 是派生索引)。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| 路径 `card_id` 不存在 | 404, `card <cid> not found` |
| `session_id` 前缀错 | 400, `invalid session_id prefix` |
| `position_id` 给了但前缀错 | 400, `invalid position_id prefix` |

---

## GET /v4/cards/{card_id}/sessions

列这张卡的所有出处 session。

### 响应

```json
{
  "card_id": "card_01jz8k2m",
  "sessions": [
    {"session_id": "sess_abc", "position_id": "pos_01jzp3nq", "indexes": "11-15", "created_at": "2026-05-24T09:12:03Z"},
    {"session_id": "sess_def", "position_id": "",            "indexes": "30-31", "created_at": "2026-05-24T09:40:00Z"}
  ]
}
```

---

## GET /v4/sessions/{session_id}/cards

**反查**:这个 session 启发了哪些卡 / 答案(`session_id` 上有索引,这正是出处从 JSON 改扁平表后能 join 的收益)。

### 响应

```json
{
  "session_id": "sess_abc123",
  "cards": [
    {"card_id": "card_01jz8k2m", "position_id": "pos_01jzp3nq", "indexes": "11-15", "created_at": "2026-05-24T09:12:03Z"}
  ]
}
```

### 错误

| 情况 | 状态 |
|---|---|
| 路径 id 前缀错 | 400 |
