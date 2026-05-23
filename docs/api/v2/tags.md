# Tags API

v2 tag 同时作用于 **session** 和 **card**，每个 tag 由 **key + value**
两个字段构成。endpoints 走 resource-rooted 路由，subject 在 URL path 里。

> **管理型标签，不参与检索。**
> tag 是给人/工具用的"标注 / 分类 / 状态位"，**不进入 search 也不进入 recall**：
> - search 的 BM25 + 向量索引来源于 round 内容和 card summary，不读 tag 字段。
> - recall 命中候选不会因为 tag 匹配而被加权或召回。
> 想用 tag 做"只看 `project:foo` 的 session"这种过滤，请走未来的 `list` / `filter` 类接口（基于元数据查询），而不是 search/recall。

## Endpoints 概览

| 操作 | 端点 |
|---|---|
| Add / Update tags on a session | `POST /v2/sessions/{session_id}/tags` |
| Remove tags from a session | `DELETE /v2/sessions/{session_id}/tags?key=...&key=...` |
| Add / Update tags on a card | `POST /v2/cards/{card_id}/tags` |
| Remove tags from a card | `DELETE /v2/cards/{card_id}/tags?key=...&key=...` |

`{session_id}` 必须以 `sess_` 开头，`{card_id}` 必须以 `card_` 开头（路由层就拒绝其它前缀）。session 和 card 的 tag 集合**互相独立**——给某 session 加 `project:foo` 不会同时给任何 card 加。

行为（解析、upsert、事件 payload 形态）对两类对象**完全相同**。下文用 session 举例，card 同理把 `/sessions/{session_id}/` 换成 `/cards/{card_id}/` 即可。

## Tag 格式（key:value）

请求里 `tags` 数组的每一项是字符串，格式：

| 输入字符串 | 解析结果 |
|---|---|
| `project:memory.talk` | `key=project`, `value=memory.talk` |
| `decision` | `key=decision`, `value=""` |
| `version:` | `key=version`, `value=""` |
| `path:/etc/hosts:rw` | `key=path`, `value=/etc/hosts:rw`（按**首个**`:` 分割）|

规则：

- 按**首个** `:` 分割，所以 value 里允许有 `:`。
- 不带 `:` 时 value 为空字符串。
- key 和 value 在解析时各自 `strip()` 去掉首尾空白。
- key 不能为空（`":foo"` / `":"` / `""` / `"   :foo"` 都视为 key 为空）。

## 存储形态

每个对象（session 或 card）的 `tags` 在内部按 **key 唯一**存储，集合形如：

```json
{
  "project": "memory.talk",
  "decision": "",
  "owner": "alice"
}
```

key 是主键，**同一对象同一 key 不会重复**，后写覆盖前写的 value。

tag 数据不进入 FTS / 向量索引，所以**改 tag 不会触发 rebuild**。

## POST /v2/sessions/{session_id}/tags

**Upsert 语义**：key 不存在 → 新增；key 已存在但 value 不同 → 覆盖 value；key 已存在且 value 相同 → 静默 noop。

```http
POST /v2/sessions/sess_187c6576/tags
Content-Type: application/json

{
  "tags": ["project:memory.talk", "decision"]
}
```

card 同款：

```http
POST /v2/cards/card_01KQ11Y1PCJ08AC0P0GA345G2Q/tags
Content-Type: application/json

{
  "tags": ["topic:lancedb", "status:reviewed"]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `tags`（body）| 是 | 至少一项，元素为 `key` 或 `key:value` 格式字符串 |

行为：

- **新增 key**（key 不存在）→ 写入 `(key, value)`，发 `tag_added` 事件，事件 payload `{"key": "...", "value": "..."}`。
- **更新 value**（key 已存在，value 不同）→ 覆盖 value，发 `tag_updated` 事件，事件 payload `{"key": "...", "value": "<新值>", "prior_value": "<旧值>"}`。
- **完全相同**（key 已存在且 value 相同）→ 不发事件、不写盘。
- 同一请求里出现重复 key → **后写覆盖**前写，整请求按数组顺序逐项处理。
- 事件挂在 URL 里那个对象身上（card 的事件不会落到 session 上，反之亦然）。

响应：

```json
{
  "status": "ok",
  "tags": [
    {"key": "project", "value": "memory.talk"},
    {"key": "decision", "value": ""}
  ]
}
```

返回 `tags` 是本次操作之后该对象上的**全部 tag**（不是增量），按对象上 key 的插入顺序排列（已有 key 在前、新 key 在后）。**不**回显 subject id —— URL 已经是真相来源。

## DELETE /v2/sessions/{session_id}/tags

**按 key 移除**。要删的 key 列表通过 query string 的 `key` 参数（可重复）传入，**不带 body**。

```http
DELETE /v2/sessions/sess_187c6576/tags?key=decision&key=project
```

card 同款：

```http
DELETE /v2/cards/card_01KQ11Y1PCJ08AC0P0GA345G2Q/tags?key=topic
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `key`（query, repeatable）| 是 | 要删除的 key，至少一个；多个写多次：`?key=a&key=b` |

行为：

- 不存在的 key 静默跳过，幂等。
- 每个**真正移除**的 key 发一条 `tag_removed` 事件，payload 包含被删除时的 value：`{"key": "...", "value": "<移除前的 value>"}`。
- query 里只接受 key，**没法**指定"value 等于 X 时才删"。如果你需要条件删除，先 GET 校验再 DELETE。

响应：

```json
{
  "status": "ok",
  "tags": [{"key": "owner", "value": "alice"}]
}
```

## 直接更新某个 tag 的 value

没有专门的 `update` 端点 —— `POST` 即可（upsert 语义）：

```http
POST /v2/sessions/sess_187c6576/tags
Content-Type: application/json

{"tags": ["project:memory.talk-v2"]}
```

如果 `project` 已经存在且 value 不同，触发 `tag_updated` 事件并覆盖；若不存在，则等同于新增（触发 `tag_added`）。

清空一个 key 的 value（保留 key、value 改成空串）：

```json
{"tags": ["project:"]}
```

完全删除一个 key（连同 value 一起去掉）：用 `DELETE`。

## 错误

| 情况 | 状态码 | detail |
|---|---|---|
| URL 里的 `{session_id}` 不以 `sess_` 开头 | 404 | `not found`（路由不匹配）|
| URL 里的 `{card_id}` 不以 `card_` 开头 | 404 | `not found`（路由不匹配）|
| 目标 session / card 不存在 | 404 | `session not found: <id>` 或 `card not found: <id>` |
| `tags`（POST body）为空数组、非字符串数组 | 400 | `tags must be non-empty` |
| 任一 tag 字符串解析后 key 为空（`""` / `":foo"` / `":"`）| 400 | `tag key cannot be empty: <原始字符串>` |
| `key`（DELETE query）一个都没有 | 400 | `at least one key required` |

## 事件 payload 速查

事件挂在被打标的对象（session **或** card）上，payload shape 与对象类型无关：

| event kind | payload | 触发时机 |
|---|---|---|
| `tag_added` | `{"key": "...", "value": "..."}` | POST 请求里**新引入**一个 key |
| `tag_updated` | `{"key": "...", "value": "<新>", "prior_value": "<旧>"}` | POST 请求**改写**了已有 key 的 value |
| `tag_removed` | `{"key": "...", "value": "<删前 value>"}` | DELETE 请求**真正**删除了一个存在的 key |

idempotent 的请求（POST 不变 / DELETE 不存在的 key）**不**产生任何事件。
