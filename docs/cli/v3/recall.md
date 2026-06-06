# recall

**无意识召回**的命令族。三个子命令:

| 子命令 | 用途 |
|---|---|
| [`recall hook`](#memorytalk-recall-hook) | 运行时:harness hook 调它,把当前 prompt 喂进来,返回 top-K 相关 card |
| [`recall list`](#memorytalk-recall-list) | 排查:看哪些 session 有 recall 历史 |
| [`recall read`](#memorytalk-recall-read-session_id) | 排查:看某个 session 的 recall 时间线 |

机制 / 设计细节(去重、`--source` 命名空间、file vs SQLite 分层)见 [`../../works/v3/recall-pipeline.md`](../../works/v3/recall-pipeline.md) 和 [`../../works/v3/session-namespace.md`](../../works/v3/session-namespace.md)。

---

## `memory.talk recall hook`

两种调用姿势二选一:

```bash
# 1. hook 模式:stdin 喂 JSON payload(host AI CLI 装的就是这个)
echo '{"session_id":"...","prompt":"...","cwd":"..."}' \
  | memory.talk recall hook --source claude-code

# 2. 手动模式:位置参数(调试 / cron / 任意自动化)
memory.talk recall hook --source claude-code [--location PATH] \
  <session_id> <prompt> [--top-k N] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--source` | **必填** | host adapter 名(`claude-code` / `codex` / ...) |
| `--location` | adapter `DEFAULT_LOCATION` | host 的 session 文件根目录;多 endpoint 用户需显式传 |
| `<session_id>` | — | hook 模式从 stdin 拿;手动模式必填。raw upstream id |
| `<prompt>` | — | 同上 |
| `--top-k` | 3 | 召回上限 |
| `--json` | 关 | 输出 JSON 而非 Markdown |

### Markdown 输出(hook 注入用)

````markdown
```bash
# Relevant memories — run any to expand detail:
memory.talk read card_01jz8k2m  # 选定 LanceDB 做向量存储
memory.talk read card_01jzp3nq  # 异步数据库连接池实现
memory.talk read card_01jzq7rm  # 搜索引擎核心原理
```
````

整段是一个 `bash` 代码块。命中 0 条 → **stdout 空字符串**(不打"无结果"占位)。

### JSON 输出(`--json`)

```json
{
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "query": "我想用 LanceDB 替换 Pinecone 怎么改",
  "recalled": [
    {"card_id": "card_01jz8k2m", "insight": "选定 LanceDB 做向量存储"},
    {"card_id": "card_01jzp3nq", "insight": "异步数据库连接池实现"}
  ],
  "skipped_already_recalled": ["card_01jz9q3w"]
}
```

`recalled[*]` 只含 `card_id` + `insight`;`skipped_already_recalled` 列被去重过滤掉的 card_id。

### 失败模式

| 情况 | exit | 行为 |
|---|---|---|
| stdin 不是 JSON | 0 | stderr 警告 + stdout 空 hookSpecificOutput(hook 契约:**永不 exit 非 0**) |
| 后端不可达 | 0 | 同上 |
| `--source` 缺失 | 2 | Click 拦截 |
| 位置参数模式下 `<session_id>` 或 `<prompt>` 缺失 | 2 | Click 拦截 |

---

## `memory.talk recall list`

```bash
memory.talk recall list [--limit N] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--limit` | 20 | 列表行数上限 |
| `--json` | 关 | 输出 JSON |

### Markdown 输出

````markdown
# recall · **5 active sessions**

| session_id                                  | recalls | unique cards | last recall          |
|---|---|---|---|
| `sess_187c6576-875f-4e3e-8fd8-f21fe60190b0` |      12 |            7 | 2026-05-31 06:42:01 |
| `sess_a3f2e1b9-4408-...`                    |       4 |            3 | 2026-05-30 23:11:08 |
| `sess_c8d1b34e-0029-...`                    |       2 |            2 | 2026-05-30 14:55:00 |
````

空列表 → `# recall · no recall history`。

### JSON 输出

```json
{
  "sessions": [
    {
      "session_id": "sess_187c6576-...",
      "recalls": 12,
      "unique_cards": 7,
      "last_recall": "2026-05-31T06:42:01+08:00"
    }
  ]
}
```

---

## `memory.talk recall read <session_id>`

```bash
memory.talk recall read <session_id> [--limit N] [--reverse] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<session_id>` | — | raw id 或带前缀都接受;服务端 normalize |
| `--limit` | 50 | 最多展示的 recall 事件数 |
| `--reverse` | 关 | 默认按时间顺序(老 → 新);加 `--reverse` 倒序 |
| `--json` | 关 | JSON |

### Markdown 输出

````markdown
# recall · `sess_187c6576-875f-4e3e-...`

**3 recalls** · first 2026-05-31 06:40:12 · last 2026-05-31 06:43:15

---

## [1] 2026-05-31 06:40:12

> 我想用 LanceDB 替换 Pinecone 怎么改

**returned**:
- `card_01jz8k2m`  选定 LanceDB 做向量存储
- `card_01jzp3nq`  异步数据库连接池实现

**skipped** (already recalled this session): _none_

---

## [2] 2026-05-31 06:42:01

> 那 migration script 怎么写

**returned**:
- `card_01jzq7rm`  搜索引擎核心原理

**skipped**: `card_01jz8k2m`, `card_01jzp3nq` (already recalled)
````

### JSON 输出

```json
{
  "session_id": "sess_187c6576-...",
  "events": [
    {
      "event_id": "01jzr1...",
      "ts": "2026-05-31T06:40:12+08:00",
      "prompt": "我想用 LanceDB 替换 Pinecone 怎么改",
      "returned": [
        {"card_id": "card_01jz8k2m", "insight": "选定 LanceDB 做向量存储"}
      ],
      "skipped_already_recalled": []
    }
  ]
}
```

### Session 不存在

打 `# recall · \`sess_xxx\` — no recall history` 一行,**exit 0**(没召回过不是错)。

---

## 错误

| 情况 | 子命令 | 行为 |
|---|---|---|
| `hook` stdin 不是 JSON | hook | stderr 警告 + 空 hookSpecificOutput,exit 0 |
| `hook` 后端不可达 | hook | 同上 |
| `list` / `read` `--limit` 无效 | list / read | Click 拦截,exit 2 |
| `read` session_id 不存在 / 无 history | read | 打 "no recall history" 一行,exit 0 |

---

## 推荐姿势

```bash
# AI host 用(setup 自动配好,一般不直接敲)
memory.talk recall hook --source claude-code   # stdin JSON

# 手动测一下某 prompt 会召回什么
memory.talk recall hook --source claude-code test-session "我想优化向量搜索"

# 看最近哪些 session 在用 recall
memory.talk recall list

# 排查某个 session 为什么 recall 不给力
memory.talk recall read sess-187c6576-...
```
