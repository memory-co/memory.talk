# Session Marks API

逐 round 打注解(mark)的写入端点。一次提交 = 一个 round 的一份 mark;`mark` 文本里 `#…？` 自动建卡 / 关联老卡,出处落 [`card_sessions`](../../structure/v4/card-session.md)。机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md),数据结构见 [`../../structure/v4/session-mark.md`](../../structure/v4/session-mark.md),CLI 见 [`../../cli/v4/session.md#session-mark`](../../cli/v4/session.md#session-mark)。

```
Submit   POST  /v4/sessions/{session_id}/marks      提交一份 mark(乐观锁 last_index)
List     GET   /v4/sessions/{session_id}/marks      列这个 session 的所有 mark(元信息)
```

> 读单条 mark 走 [`POST /v4/read`](read.md)(`{"id": "sess_…#m1"}`,按 `#` 分片判型);反查「这条 mark 启发了哪些卡」走 [`GET /v4/sessions/{session_id}/cards`](sessions.md#get-v4sessionssession_idcards)。

## POST /v4/sessions/{session_id}/marks

提交一个 round 的一份 mark。**乐观锁**:`last_index` 与 session 当前最新 round index 不一致 → 整份拒绝(409)。

### 请求体

```json
{
  "last_index": 41,
  "description": "在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么",
  "marks": [
    {"id": "m1", "indexes": "36-37", "mark": "配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？\n他其实想要可重连会话。"},
    {"id": "m2", "mark": "这段在排查 EMFILE,跟句柄上限有关。"}
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `last_index` | 是 | 提交时读到的 session 最新 round index(乐观锁基线) |
| `description` | 是 | 这次标注的场景;随每条 mark 落盘 |
| `marks[]` | 是 | 非空数组,每条 `{id, mark, indexes?}`;`mark` 里 `#…？` = 问题 |
| `marks[].id` | **是** | mark id `m<n>`,**每条显式给、不默认分配**。session 内单调、不跳号 / 不复用(续标接着上次最大序号往后;不知道当前最大就先 `GET …/marks`) |
| `marks[].indexes` | **含 `#…？` 时必给** | 这条 mark 的 `#…？` grounding 的 round(s)——问题从哪几轮读出来的;可多个,语法同 `reviews.indexes`(`36-37` / `3,7,12`)。落进 `card_sessions.indexes`(那条 mark 建/连的卡都用它)。无 `#…？` 的 mark 不需要 |

> wire 也接受 YAML（CLI 直接转发);字段同上。

### 副作用(写入顺序)

1. **乐观锁校验**:`last_index` == session `max(round_index)`?否 → 409,不写任何东西。
2. 按提交里每条的 `id`(`m<n>`)→ 落 `marks/<id>.yaml`(canonical · YAML)+ 插一行 `session_marks`(`id` 缺失 / 跳号 / 复用 → 400,整份拒绝)。
3. 解析每条 `mark` 的 `#…？` → embed 撞 `cards`(issue)向量库,按三岔:
   - **miss → 建新卡**(读 session 抽卡的入口;**另有**显式 [`POST /v4/cards`](cards.md) 用于不从 session 来的卡,如质疑另一问题):`issue` = 该 `#…？` 的问题文本(非空)、自动生成 `card_id` = `card_<ULID>`、embed `issue` 写 `cards` collection、落 `cards/<bucket>/<card_id>/card.json`(canonical:`issue` + `created_at`,**创建即冻**)。
   - **hit → 关联**老卡(不动老卡)。
   - 两种都各记一条 [`card_sessions`](../../structure/v4/card-session.md):`mark` = `m<n>` + `indexes` = 这条 `#…？` grounding 的 round(s)(出处指 `(session_id, mark)`,记录它从哪几轮来)。embedding provider 失败 → 该问题建卡**降级**(见 503),不阻塞整份提交。

### 响应 `200`

```json
{
  "session_id": "sess_def456",
  "last_index": 41,
  "marks": [
    {"mark": "m1", "issues": [{"issue": "为什么 pty 会让用户想到 tmux", "card_id": "card_01jz8k2m", "is_new": true, "indexes": "36-37"}]},
    {"mark": "m2", "issues": []}
  ]
}
```

### 状态码

| 码 | 情况 |
|---|---|
| `200` | 提交成功 |
| `400` | `marks` 为空 / body 非法 / `id` 缺失 / 跳号 / 复用 |
| `404` | `session_id` 不存在 |
| `409` | `last_index` ≠ session 当前最新 round index(标注期间来了新 round;重读再标) |
| `503` | 服务未就绪(searchbase 缺失时 `#…？` 建卡降级,详见 [cards.md](cards.md) 的 best-effort 约定) |

## GET /v4/sessions/{session_id}/marks

列这个 session 的所有 mark(**元信息**,来自 `session_marks`;正文不回,要看正文走 `read sess_…#m1`)。

### 响应 `200`

```json
{
  "session_id": "sess_def456",
  "marks": [
    {"mark": "m1", "last_index": 41, "created_at": "2026-06-16T08:30:00Z"},
    {"mark": "m2", "last_index": 41, "created_at": "2026-06-16T08:30:00Z"}
  ]
}
```

> **状态:设计提案,未实施**(同 [session-mark.md](../../works/v4/session-mark.md))。
