# Sessions API

Session ingest is **cursor-based + append-only**. Two endpoints; the
caller (sync watcher, or any external adapter pushing data) is expected
to read the server's cursor first, then send only what's strictly new.

There is **no public "read a session" endpoint** — reads go through
`POST /v3/search` → `POST /v3/read`.

> Pre-PR-2 there was a single whole-session `POST /v3/sessions` that
> internally diffed against `rounds_index` and reported
> `action=imported|appended|skipped|partial_append`. That shim is gone.
> The mental model is now: **sync owns the cursor (sha256 +
> last_round_id + line_offset), ingest is a dumb append target with
> optimistic concurrency.**

`session_id` in request bodies is the **raw platform id** (no `sess_`
prefix); responses always carry the **prefixed** form (`sess_<raw>`).
Adapters can pass either shape — the server normalizes.

## POST /v3/sessions/ensure

Read-only probe. Returns the server's current cursor for a `(source,
session_id)`, so the caller knows where to resume from before it reads
the upstream file/URL.

### Request

```json
{
  "session_id": "187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "source": "claude-code"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 平台原始 id,无前缀 |
| `source` | 是 | 平台来源 (`claude-code` / ...) |

### Response

```json
{
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "last_round_id": "a7c01e0e-…",
  "round_count": 42
}
```

| 字段 | 说明 |
|---|---|
| `session_id` | 已加前缀的 session id |
| `last_round_id` | 服务端已存 session 的最后一个 round 的 `round_id`,或 `null`(首次见到这个 session) |
| `round_count` | 服务端当前 round 数(0 表示 session 尚不存在) |

### 副作用

无。纯只读。

---

## POST /v3/sessions/append

写新 rounds 到一个 session 的末尾。**乐观锁** —— 调用方必须把它认为的"上一次最后一个 round_id"传进来,服务端比对成功才追加。

### Request

```json
{
  "session_id": "187c6576-…",
  "source": "claude-code",
  "expected_prev_round_id": "a7c01e0e-…",
  "rounds": [
    {
      "round_id": "b9001234-…",
      "parent_id": "a7c01e0e-…",
      "timestamp": "2026-05-20T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [{"type": "text", "text": "follow-up question"}],
      "is_sidechain": false,
      "cwd": "/home/user/myapp"
    }
  ],
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {
    "cwd": "/home/user/myapp",
    "project": "myapp"
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 平台原始 id |
| `source` | 是 | 平台来源 |
| `expected_prev_round_id` | 是 | 调用方认为的服务端当前游标。**首次写入这个 session 时传 `null`**。 |
| `rounds` | 是 | 严格在 `expected_prev_round_id` 之后的新 rounds(按时间顺序)。可以为空(只刷新元数据)。 |
| `created_at` | 否 | 首次写入(`expected_prev_round_id=null`)时用于建 session 行;之后调用忽略。 |
| `metadata` | 否 | 每次刷新 session 元数据。`metadata.cwd` 影响 explore namespace 判定。 |

Round / ContentBlock 结构见 [`../../structure/v3/session.md`](../../structure/v3/session.md)。`round.index` 由服务端按 append 顺序赋值,调用方不传。

### Response — 成功

```json
{
  "status": "ok",
  "session_id": "sess_187c6576-…",
  "new_last_round_id": "b9001234-…",
  "appended_count": 1,
  "round_count": 43
}
```

| 字段 | 说明 |
|---|---|
| `status` | `"ok"` |
| `session_id` | 已加前缀 |
| `new_last_round_id` | 追加后的服务端游标。下一次调用 `expected_prev_round_id` 应该传这个。 |
| `appended_count` | 本次实际追加的 round 数 |
| `round_count` | session 当前总 round 数(含本次) |

### Response — 冲突

服务端的实际 `last_round_id` ≠ 调用方传的 `expected_prev_round_id` 时:

```json
{
  "status": "conflict",
  "session_id": "sess_187c6576-…",
  "actual_last_round_id": "a7c01e0e-NEWER-…",
  "appended_count": 0,
  "round_count": 0
}
```

**调用方义务**:用 `actual_last_round_id` 当新游标,重新从上游读 strictly-after 的 rounds,再发一次。memory.talk 内置的 SyncWatcher 会自动重试一次,第二次仍冲突就打 error 日志并放弃这一轮(下个事件再来)。

| 字段 | 说明 |
|---|---|
| `status` | `"conflict"` |
| `actual_last_round_id` | 服务端真实游标 |
| `appended_count` | 永远为 0(冲突场景下啥都没写) |

### 副作用 — 仅在 `status=ok` 且 `appended_count > 0` 时发生

- 追加 `sessions/{source}/{id[0:2]}/{prefixed_session_id}/rounds.jsonl`
- 更新 `sessions/{...}/meta.json`
- 更新 SQLite `sessions` 表(`round_count` + `last_round_id` + `synced_at`)
- 写 LanceDB `rounds` 表(text + vector,best-effort,失败只记 event 不阻塞)
- 向 `events.jsonl` 追加 `imported`(首次)或 `rounds_appended`(后续)

### 错误

| 情况 | 状态 |
|---|---|
| `rounds` 结构非法 | 400 |
| `rounds[].round_id` 缺失 | 400 |

---

## GET /v3/sessions

List session 元数据(**不带 rounds**)。CLI 入口 [`memory.talk session list`](../../cli/v3/session.md#session-list)。

### 查询参数

所有参数都可选,**默认列全部 session**(按 `created_at` 倒序,截 `limit`)。多参数 AND。

| 参数 | 类型 | 说明 |
|---|---|---|
| `source` | string | adapter 名(精确匹配)。e.g. `?source=claude-code` |
| `endpoint` | string | `<source>@<label>`。比 `source` 更细;label 不传时回退到 `location`,所以这里也接受 `<source>@<location>` 形式 |
| `cwd` | string | `metadata.cwd` 前缀(完全展开后的绝对路径)。前缀匹配,**不**正则 |
| `tag` | string,重复可叠 | `K=V` 严格匹配 / `K` 只校验 key 存在。多个 `tag` AND。e.g. `?tag=project=billing&tag=status=wip` |
| `since` | ISO 8601 | `created_at >= since`。CLI 端的 `7d` / `12h` duration 在 CLI 层解析成 ISO 后再传 |
| `until` | ISO 8601 | `created_at <= until` |
| `limit` | int,默认 `20`,上限 `200` | 返回多少条 |

### 响应

```json
{
  "total": 1247,
  "returned": 23,
  "sessions": [
    {
      "session_id": "sess-15f0a7fb-...190b0",
      "source": "claude-code",
      "endpoint": "claude-code@/home/user/.claude/projects",
      "location": "/home/user/.claude/projects",
      "location_label": "/home/user/.claude/projects",
      "cwd": "/home/user/work/billing-svc",
      "created_at": "2026-05-24T09:12:03Z",
      "synced_at": "2026-05-24T09:45:11Z",
      "round_count": 47,
      "tags": {"project": "billing", "status": "wip"}
    }
  ]
}
```

- `total` 是匹配条件的总数(不受 `limit` 截断,服务端 `COUNT(*)` 取得);客户端用来提示"还有更多,加大 limit"。
- `returned == len(sessions)`,等于 `min(total, limit)`。
- `tags` 是个 string→string 字典,空字典 `{}` 表示无 tag。

### 错误

| 情况 | 状态 |
|---|---|
| `limit` 超出 `[1, 200]` | 400 |
| `since` / `until` 不是合法 ISO 8601 | 400 |
| `since` / `until` 时间窗反向(since > until) | 400 |
| `tag` 串里出现非法 key | 400 |

---

## PATCH /v3/sessions/{session_id}/tags

设 / 删 session 的 kv 标签,**PATCH 语义**(只动声明的 key,不传的 key 原样保留)。CLI 入口 [`memory.talk session tag`](../../cli/v3/session.md#session-tag)。

### 请求体

```json
{
  "set":   {"project": "billing", "status": "wip"},
  "unset": ["draft", "obsolete"]
}
```

- `set`(可选,默认 `{}`):key→value 字典。已存在的 key 覆盖,不存在的 key 新增。
- `unset`(可选,默认 `[]`):要删除的 key 列表。key 不存在时**静默忽略**(不报错)。
- **两个都不传 / 都空 = 查询当前 tags 的语法糖**。等同于 `GET` 该 session 的 `.tags`(我们没单独开一个 GET — `session tag <sid>` 不带任何参数走的就是 PATCH `{}, {}`)。

### 约束(全部由服务端校验)

| 约束 | 报错 |
|---|---|
| key 必须匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$` | 400 `tag key '<k>' invalid` |
| value 长度 ≤ 200 char | 400 `tag value for '<k>' too long (max 200)` |
| 单 session tag 总数 ≤ 50(以 PATCH 后的最终量算) | 400 `too many tags (max 50)` |
| 同 key 同时出现在 `set` 和 `unset` | 400 `cannot both set and unset '<k>'` |
| session_id 不存在 | 404 |

任一违反 → **整次 PATCH 拒绝**,SQLite 不改。

### 响应

返回**改动后的全量 tags**(方便消费方拿到最终状态,不用回查):

```json
{
  "session_id": "sess-15f0a7fb-...190b0",
  "tags": {"project": "billing", "status": "wip"}
}
```

### 副作用

- 改写 SQLite `sessions.tags`。
- 不改 `metadata`(metadata 是平台原生字段,tag 是用户字段,两者解耦)。
- 不动 `rounds.jsonl` / LanceDB / events.jsonl —— tag 是元数据,不是对话事件。

---

## 调用方

- **内部**: `memorytalk.service.sync.SyncWatcher` 通过 in-process 直接调 `IngestService.ensure_session` / `append_rounds`,不走 HTTP。
- **外部**: 任何想从 v3 之外的来源往 memory.talk 灌 session 的程序(CI runner / 自定义脚本 / 将来 sync 服务变 remote 后的 client)走这两个 HTTP 路由。

## 跟 PR-1 之前的差异

| | 旧 (whole-session shim) | 新 (cursor) |
|---|---|---|
| 入口 | 单个 `POST /v3/sessions` | `POST /v3/sessions/ensure` + `POST /v3/sessions/append` |
| 调用方负担 | 把整 session 发过来,服务端帮你 diff | 自己读游标 / 自己算增量 |
| sha256 | 请求体里必传,服务端用于 short-circuit | **不传**;sync 自己在 sync.db 维护 |
| 已存 round 内容变了 | `rounds_overwrite_skipped` 事件 | **不检测**(append-only 假设),静默忽略 |
| 失败信号 | `action=skipped` | `status=conflict` + `actual_last_round_id` |

新协议把"上游连接器状态"和"持久化数据状态"切干净 —— ingest 只懂 append,sync 全权负责"哪些是新的"。
