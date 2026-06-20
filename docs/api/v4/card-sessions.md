# Card-Sessions API

**card→session 出处**关系:哪个 session 的**哪条 mark**(的 `#…？`)**建 / 连**了这张卡。这是**卡(问题)级**的关系,经 **mark**,和 [card↔card 的 links](card-links.md) 平行,都嵌在卡下(`/v4/cards/{card_id}/...`)。支持多 session、同一对多条(不同 mark)。

> **这里只有 card→session,跟 Position 无关。** 答案级的出处(某个 Position 来自哪几轮)是**另一条链路** `position_sessions`(经 round `indexes`、`mark` 可选),由 [`POST /v4/cards/{card_id}/positions`](cards.md#post-v4cardscard_idpositions) 的 `source` 写入,见 [`../../structure/v4/position-session.md`](../../structure/v4/position-session.md)。别把两者塞进一张表。

CLI 一般不直接调——card→session 由 **mark 写路径自动写入**:[`session mark`](../../cli/v4/session.md#session-mark) 里 `#…？` miss 建新卡 / hit 连老卡时,各记一条 `card_sessions`,`mark` 列 = 那条 mark 的 id。本页端点用于显式记录和反查。字段语义详见 [`../../structure/v4/card-session.md`](../../structure/v4/card-session.md)。

> SQLite 表名 `card_sessions`(API 路径嵌到卡下)。canonical 是 mark 的 `questions[]`(file,`marks/m<n>.yaml`),这张表是它的派生 join 索引。

---

## POST /v4/cards/{card_id}/sessions

给 `{card_id}` 显式记一条 card→session 出处(指明是哪条 mark)。

### 请求体

```json
{
  "session_id": "sess_abc123",
  "mark": "m1"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 哪个 session,`sess_<...>`。**扁平列、可 join、无 FK** |
| `mark` | 是 | 哪条 mark 建 / 连的;mark id `m<n>`(session 内序号,全址 `{session_id}#{mark}`)。**精确到那条带 `#…？` 的感悟**——`card_sessions` 颗粒度必到 mark(支撑 `#…？` 双向关联) |

(卡 = 路径里的 `{card_id}`。)

### 主键 / 多值

主键 `(card_id, session_id, mark)`:同一卡可被同一 session 的**多条不同 mark** 建 / 连(各记一条);也支持多 session。重复 → 幂等。

### 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m", "session_id": "sess_abc123", "mark": "m1"}
```

### 副作用

- 校验路径 `card_id` 存在、`session_id` 前缀合法、`mark` 是该 session 已有的 mark → 失败不落库。
- 写一行 `card_sessions`。
- **不加 FOREIGN KEY**(容忍悬挂 `session_id` / `mark`——SQLite 是派生索引)。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| 路径 `card_id` 不存在 | 404, `card <cid> not found` |
| `session_id` 前缀错 | 400, `invalid session_id prefix` |
| `mark` 不是该 session 的 mark | 400, `invalid mark` |

---

## GET /v4/cards/{card_id}/sessions

列这张卡的所有出处:哪些 session 的哪条 mark 建 / 连了它。

### 响应

```json
{
  "card_id": "card_01jz8k2m",
  "sessions": [
    {"session_id": "sess_abc", "mark": "m1", "created_at": "2026-05-24T09:12:03Z"},
    {"session_id": "sess_def", "mark": "m3", "created_at": "2026-05-24T09:40:00Z"}
  ]
}
```

---

## GET /v4/sessions/{session_id}/cards

**反查**:这个 session(的哪条 mark)建 / 连了哪些卡(`session_id` 上有索引,这正是出处从 JSON 改扁平表后能 join 的收益)。

### 响应

```json
{
  "session_id": "sess_abc123",
  "cards": [
    {"card_id": "card_01jz8k2m", "mark": "m1", "created_at": "2026-05-24T09:12:03Z"}
  ]
}
```

### 错误

| 情况 | 状态 |
|---|---|
| 路径 id 前缀错 | 400 |
