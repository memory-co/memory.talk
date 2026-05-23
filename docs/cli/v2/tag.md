# tag

给 session 或 card 加 / 改 / 删 tag。tag 是 **key + value** 形态的管理型标签。

> **不参与检索。**
> tag **不进 search、也不进 recall**——它是给人/工具用的标注，不是给模型用的语义信号。改 tag 也**不会触发 rebuild**。想做"按 tag 过滤"用未来的 `list` / `filter` 类元数据查询接口。

完整结构见 [`docs/structure/v2/tag.md`](../../structure/v2/tag.md)，HTTP API 见 [`docs/api/v2/tags.md`](../../api/v2/tags.md)。

## 语法

每个 tag 在 CLI 上写成 `key:value` 字符串：

| 写法 | 解析 |
|---|---|
| `project:memory.talk` | `key=project`, `value=memory.talk` |
| `decision` | `key=decision`, `value=""` |
| `version:` | `key=version`, `value=""`（同 `decision`）|
| `path:/etc/hosts:rw` | `key=path`, `value=/etc/hosts:rw`（按**首个** `:` 分割，value 内允许 `:`）|

key 不能为空（`":foo"` / `":"` 会报错）；key/value 各自 strip 首尾空白。

## tag add（新增 / 更新）

**Upsert 语义** —— key 不存在则新增，已存在则覆盖 value，已存在且 value 一致则静默 noop。

```bash
memory.talk tag add <subject_id> <tag> [<tag> ...] [--json]
```

`<subject_id>` 必须以 `sess_` 或 `card_` 开头，CLI 按前缀自动选择 endpoint（内部路由到 `/v2/sessions/{sid}/tags` 或 `/v2/cards/{cid}/tags`）。

例：

```bash
# 给 session 加 tag
memory.talk tag add sess_187c6576 decision project:memory.talk

# 给 card 加 tag
memory.talk tag add card_01KQ11Y1PCJ08AC0P0GA345G2Q topic:lancedb status:reviewed

# 直接更新一个 tag 的 value（key 已存在 → 覆盖）
memory.talk tag add sess_187c6576 project:memory.talk-v2

# 把已有 key 的 value 清空（保留 key）
memory.talk tag add sess_187c6576 project:
```

### Markdown（默认）

```markdown
ok: tags = `project:memory.talk`, `decision`
```

value 为空的 tag 直接显示 key（不显示 `:`）：

```markdown
ok: tags = `decision`, `owner:alice`
```

返回的 `tags` 是本次操作之后该对象上的**全部 tag**（不是增量），按对象上 key 的插入顺序排列（已有 key 在前、新 key 在后）。

### JSON（`--json`）

```json
{
  "status": "ok",
  "tags": [
    {"key": "project", "value": "memory.talk"},
    {"key": "decision", "value": ""}
  ]
}
```

## tag remove（按 key 删除）

```bash
memory.talk tag remove <subject_id> <key> [<key> ...] [--json]
```

参数是 **key 列表**，**不**写 `key:value`——CLI 会拒绝带 `:` 的输入。如果你想"只在 value 等于 X 时才删"，本命令不支持，先 `view` 校验再 `remove`。

例：

```bash
memory.talk tag remove sess_187c6576 decision project
memory.talk tag remove card_01KQ11Y1PCJ08AC0P0GA345G2Q status
```

不存在的 key 静默跳过（幂等，log 也不记）。

### Markdown

```markdown
ok: tags = `project:memory.talk`
```

全部 tag 被清空：

```markdown
ok: tags = *(empty)*
```

### JSON

```json
{
  "status": "ok",
  "tags": [{"key": "project", "value": "memory.talk"}]
}
```

## 输出语义注意

CLI 输出**只展示当前全量 tag**，不区分本次操作是 added / updated / unchanged / removed。如果你需要审计哪个 tag 被改/被删，去看 log：

```bash
memory.talk log <subject_id>
```

事件类型：

| event kind | 触发时机 |
|---|---|
| `tag_added` | POST 引入新 key |
| `tag_updated` | POST 改写已有 key 的 value（payload 含 `prior_value`） |
| `tag_removed` | DELETE 真正删了一个存在的 key |

**幂等请求不发事件**（POST 同 key 同 value、DELETE 不存在的 key）。

## 错误

| 情况 | 状态 |
|---|---|
| `<subject_id>` 不以 `sess_` / `card_` 开头 | 400，`subject_id must start with sess_ or card_` |
| 目标 session / card 不存在 | 404，`session not found: <id>` 或 `card not found: <id>` |
| `tags` 参数为空（CLI 一个都没给）| Click 拦截，`Missing argument 'TAGS...'` |
| add 请求里某个 tag 字符串解析后 key 为空（`":foo"` / `":"`）| 400，`tag key cannot be empty: <原始字符串>` |
| remove 请求里某个 key 含 `:` | 400，`tag remove takes keys only, not key:value` |

错误展示：

```markdown
**error:** subject_id must start with sess_ or card_
```

`--json`:

```json
{"error": "subject_id must start with sess_ or card_"}
```
