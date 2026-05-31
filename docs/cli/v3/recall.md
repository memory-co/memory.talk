# recall

**无意识召回**的命令族。三个子命令:

| 子命令 | 用途 |
|---|---|
| [`recall hook`](#memorytalk-recall-hook) | 运行时:harness hook 调它,把当前 prompt 喂进来,返回 top-K 相关 card |
| [`recall list`](#memorytalk-recall-list) | 排查:看哪些 session 有 recall 历史(in-flight + 已 sync 的都算) |
| [`recall read`](#memorytalk-recall-read-session_id) | 排查:看某个 session 的 recall 时间线 —— 每次的 prompt + 返回了什么 + 被去重跳过的是什么 |

> 没有顶层 `memory.talk recall <session_id> <prompt>` 这种姿势了 —— 那是旧 0.8.x 的接口,合并进 `recall hook` 的位置参数(仍然支持手动调试)。
>
> hook 集成路径要从 `memory.talk recall --hook` 改成 `memory.talk recall hook`。setup 装的 plugin assets 会跟着更新,旧 host plugin 在 setup re-install 时自动覆盖。

---

## `memory.talk recall hook`

跟旧 `recall` 完全等价(只是被收进子命令)。两种调用姿势二选一:

```bash
# 1. hook 模式:stdin 喂 JSON payload(host AI CLI 装的就是这个)
echo '{"session_id":"...","prompt":"...","cwd":"..."}' | memory.talk recall hook

# 2. 手动模式:位置参数(调试 / cron / 任意自动化)
memory.talk recall hook <session_id> <prompt> [--top-k N] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<session_id>` | — | hook 模式从 stdin 拿;手动模式必填位置参数。命名空间跟 [sync](sync.md) 一致(平台原始 id,服务端加 `sess_` 前缀) |
| `<prompt>` | — | 同上 |
| `--top-k` | 3 | 召回上限。极小是有意的:无意识召回不该塞太多稀释 prompt |
| `--json` | 关 | 输出 JSON 而非 Markdown |

### 跟 [search](search.md) 的差别

| | `search` | `recall hook` |
|---|---|---|
| 触发 | AI 推理过程主动调用 | harness hook 自动调用 |
| 意识形态 | 有意识 / 决定要查 | 无意识 / 看到 prompt 即浮现 |
| session_id | 可选(仅审计) | **必填**(去重 key) |
| 返回内容 | 完整(snippets / source / stats) | 极简(只 id + insight) |
| 命中桶 | cards + sessions | **只 cards** |
| 去重 | 无 | 同 `session_id` 已召回的卡**不再返回** |

### Markdown 输出(hook 注入用)

````markdown
```bash
# Relevant memories — run any to expand detail:
memory.talk read card_01jz8k2m  # 选定 LanceDB 做向量存储
memory.talk read card_01jzp3nq  # 异步数据库连接池实现
memory.talk read card_01jzq7rm  # 搜索引擎核心原理
```
````

约定 — 整段就是一个 `bash` 代码块:

1. 首行 bash 注释告诉 LLM 这一段是什么
2. 每条命中以**可执行命令**形式给出 —— LLM 觉得有用直接复制运行
3. insight 写在 `# ` 注释里,bash 语义对齐
4. **不打 H2 / H3 标题** —— harness 直接 inline 这段进 context,加标题等于污染 prompt
5. 命中 0 条 → **stdout 空字符串**(不打"无结果"占位)

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

`recalled[*]` 只含 `card_id` + `insight`,不含 score / snippets / source / stats / created_at —— 极简是契约。

### 副作用

- 写一条 `recall_event` 记录:`(event_id, session_id, prompt, ts, returned_card_ids[], skipped_card_ids[])`。所有去重 + 时间线视图都从这一张表导出。
- 对每张本次新返回的 card 累加 `card.stats.recall_count += 1`。被 `skipped` 跳掉的不计。
- 不发 events,不落 search_log,不写 file-layer。

### 失败模式

| 情况 | exit | stderr/stdout |
|---|---|---|
| stdin 不是 JSON(hook 模式) | 0 | stderr 警告 + stdout 空 hookSpecificOutput JSON(hook 契约:**永不 exit 非 0** 以免阻塞 LLM) |
| 后端不可达 | 0 | 同上 |
| 位置参数缺 | 2 | Click 拦截 |

---

## `memory.talk recall list`

列出**有 recall 历史的 session**,按最近 recall 时间倒序。

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
| ...                                         |     ... |          ... |                 ... |
````

- **`recalls`**: 这个 session 发生过的 `recall hook` 次数(即 `recall_event` 行数)
- **`unique cards`**: 这个 session 累计返回过的 distinct card 数量
- **`last recall`**: 最近一次 recall 的时间,本地时区

空列表:`# recall · no recall history` 一行就完。

### JSON 输出

```json
{
  "sessions": [
    {
      "session_id": "sess_187c6576-...",
      "recalls": 12,
      "unique_cards": 7,
      "last_recall": "2026-05-31T06:42:01+08:00"
    },
    ...
  ]
}
```

### 不做什么

- **不**区分 "in-flight" vs "已 sync" —— 那需要 join sessions 表 + 实时性差(sync 是异步的)。`recall list` 只看 `recall_event` 这一张表,语义清晰: "有 recall 历史的所有 session_id"。
- **不**显示 prompt 摘要 —— 那是 `recall read` 的事。

---

## `memory.talk recall read <session_id>`

展示一个 session 的 recall 时间线:每次 hook 的 prompt + 返回了什么 + 被去重跳过的是什么。

```bash
memory.talk recall read <session_id> [--limit N] [--reverse] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<session_id>` | — | raw id 或带前缀都接受;服务端 normalize |
| `--limit` | 50 | 最多展示的 recall 事件数 |
| `--reverse` | 关 | 默认按时间顺序(老 → 新);加 `--reverse` 倒序(新 → 老) |
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

---

## [3] 2026-05-31 06:43:15

> 还有什么要注意的

**returned**: _none_ (all candidates already recalled)

**skipped**: `card_01jz8k2m`, `card_01jzp3nq`, `card_01jzq7rm`
````

- 每个 recall 事件是一个 `## [N] <ts>` 块
- prompt 用 `> blockquote` 突出 —— 主角是用户问了什么
- returned / skipped 各列一段
- card insight 跟卡 id 一起显示(join 一下 cards 表),空 insight 显示 `_(no insight)_`
- 全 skipped 的事件值得显示 —— 排查"为什么这一轮没召回到"特别有用

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
        {"card_id": "card_01jz8k2m", "insight": "选定 LanceDB 做向量存储"},
        {"card_id": "card_01jzp3nq", "insight": "异步数据库连接池实现"}
      ],
      "skipped_already_recalled": []
    },
    ...
  ]
}
```

### Session 不存在

`recall read` 找不到任何 event:

```
# recall · `sess_xxx` — no recall history
```

退出码 0(不是错误 —— 就是真的没召回过)。

---

## 共享:session_id 命名空间

`recall hook` 接受的 session_id 跟 [sync](sync.md) 写入 v2 的 session_id **完全一致**(平台原始 id,如 Claude Code 的 UUID)。两个时间窗:

```
[recall 1]  hook → recall hook(sess_uuid, prompt_1)   ← session 还没被 sync 走
[recall 2]  hook → recall hook(sess_uuid, prompt_2)   ← 还没
[recall 3]  hook → recall hook(sess_uuid, prompt_3)   ← 还没
[sync]      定时器 → sync                              ← 现在才把这条 session 写进 v2
```

- recall 时,**v2 里这个 session 大概率还不存在**(sync 是异步定时的,recall 是 hook 实时的)
- 所以 `recall hook` 不要求 session 在 v2 里存在,**不查 `db.sessions.get()`、不报 404**
- `recall list` / `recall read` 也只读 `recall_event` 表,**不 join sessions** —— 你能看到的就是 hook 真的跑过的 session

---

## 数据结构 (schema 改动)

**0.9.0 引入,替换旧 `recall_log` 表。**

```sql
CREATE TABLE recall_event (
    event_id        TEXT PRIMARY KEY,    -- ULID
    session_id      TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    ts              TEXT NOT NULL,        -- UTC ISO
    returned_ids    TEXT NOT NULL,        -- JSON array of card_ids
    skipped_ids     TEXT NOT NULL         -- JSON array of card_ids
);
CREATE INDEX idx_recall_event_session_ts
    ON recall_event(session_id, ts DESC);
```

### 旧 `recall_log` 怎么处理

旧表注释明确写了 "in-memory-ish — cleared on rebuild",历史数据本来就是可丢的。0.9.0 upgrade 时:

- 旧 `recall_log` 直接 `DROP TABLE`
- 不迁移历史(反正没存 prompt,迁了也只是 (session, card) 对,read 子命令拿不出 prompt 来,残缺)
- 升级路径写在 release notes 里:**recall 历史会清空**,之后正常使用即可

### 去重逻辑

新表 + json_each 即可:

```sql
SELECT DISTINCT card_id
  FROM recall_event, json_each(recall_event.returned_ids) AS j
 WHERE recall_event.session_id = ?
   AND j.value IN (<candidate_card_ids>)
```

SQLite 有内置 `json_each`,在 `(session_id, ts DESC)` 索引下查一个 session 的所有 returned card 是 O(events × avg_cards_per_event)。recall 一般每 session 几十次 × 每次 top-3,总量百级,纯 SQLite 跑无压力。

---

## 错误

| 情况 | 子命令 | 行为 |
|---|---|---|
| `hook` stdin 不是 JSON | hook | stderr 警告 + 空 hookSpecificOutput,**exit 0**(hook 契约) |
| `hook` 后端不可达 | hook | 同上 |
| `list` `--limit` 无效 | list | Click 拦截,exit 2 |
| `read` `--limit` 无效 | read | Click 拦截,exit 2 |
| `read` session_id 不存在 / 无 history | read | 打 "no recall history" 一行,**exit 0** |

---

## 跟其它命令的边界

- **`search`** 是有意识检索,留审计、可带 `--where`、返回完整字段;`recall hook` 是无意识、极简、去重。完全两条路径,不互相调用,各自的 log 表独立。
- **`sync`** 跟 recall 异步并行 —— recall 在 sync 把 session 落 v2 之前就开始写 `recall_event`。两条线用同一个 session_id,sync 落地后 recall 历史自然挂上。
- **`read`(顶层 card/session read)** 跟 `recall read` 是不同范畴 —— 前者读单条 card / session 的内容,后者读 session 上的"被召回过几次都召了什么"事件流。子命令路径不重叠。

---

## 推荐姿势

```bash
# AI host 用(setup 自动配好,你一般不直接敲)
memory.talk recall hook   # stdin JSON

# 手动测一下某 prompt 会召回什么
memory.talk recall hook test-session "我想优化向量搜索"

# 看最近哪些 session 在用 recall
memory.talk recall list

# 排查某个 session 为什么 recall 不给力
memory.talk recall read sess_187c6576-...
```

---

## Open questions(实现前请拍板)

1. **schema rename:`recall_log` → `recall_event`**,旧表 drop 不迁移。OK?(历史本来是 "in-memory-ish",且没存 prompt 无法补)
2. **`--hook` flag 移除**:旧 `memory.talk recall --hook` 这种姿势完全砍掉,只留 `memory.talk recall hook`。setup 会更新 `hook_assets/` 里 plugin 的 `hooks.json`,用户 re-run setup 时新 plugin 覆盖旧的。OK?还是保留 `--hook` 一两个版本做兼容?
3. **`recall hook` 是否支持位置参数**(调试用):我建议保留(零额外成本),但你说话算。
4. **`recall read` 时间排序默认方向**:我建议时间顺序(老 → 新),`--reverse` 倒序。理由:read 是看"这个 session 怎么走过来的",叙事顺读更自然。
5. **0.9.0 minor bump**(因为 schema 改了)。OK?
