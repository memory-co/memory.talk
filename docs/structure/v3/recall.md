# Recall

**无意识召回**的事件流。hook 阶段每次 `memory.talk recall hook` 调用产生一条 `RecallEvent`,记录当时的 prompt + 返回了哪些 card + 哪些被去重跳过。

跟 [Review](review.md) / [Card](talk-card.md) 等"长期记忆"对象不同 —— RecallEvent 是**短期会话级**的事件流,只支持 dedup + 排查这两件事,**不参与论坛动力学**(沉浮、ranking 都不用它)。

## 一张表,single source of truth

整个 recall 子系统**只有一张表**:`recall_event`。所有视图都从这一张表导出:

| 视图 | 怎么从 `recall_event` 导出 |
|---|---|
| **dedup**(`recall hook` 决定要不要返回某 card) | `SELECT DISTINCT j.value FROM recall_event, json_each(returned_ids) j WHERE session_id = ?` |
| **session 列表**(`recall list`) | `SELECT session_id, COUNT(*), MAX(ts) FROM recall_event GROUP BY session_id` |
| **session 时间线**(`recall read <session_id>`) | `SELECT * FROM recall_event WHERE session_id = ? ORDER BY ts` |
| **card 的累计召回数**(search/read 结果旁边的 `recalls N`) | `SELECT COUNT(*) FROM recall_event, json_each(returned_ids) j WHERE j.value = ?` |

**之所以坚持 single source**:旧设计有 `recall_log`(dedup 用)+ `card_stats.recall_count`(展示用)两套数据,写路径不在一个事务里,进程崩了会**永久 drift** 且没人发现。新设计只一张表,**结构上不可能 drift**。

## Schema

```json
{
  "event_id":     "01jzr5kq8h3f1d4w9m6p2x7c0a",
  "session_id":   "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "prompt":       "我想用 LanceDB 替换 Pinecone 怎么改",
  "ts":           "2026-05-31T06:42:01Z",
  "returned_ids": ["card_01jz8k2m", "card_01jzp3nq"],
  "skipped_ids":  ["card_01jz9q3w"]
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `event_id` | string | 自动 | ULID,无前缀(只在 recall 子系统内出现,不会跟其它对象 ID 混) |
| `session_id` | string | 是 | `sess_<...>`,带前缀。**recall 不要求 session 已经在 v2 sessions 表里存在** —— 见下方"跟 [sync](sync.md) 的时序" |
| `prompt` | string | 是 | 用户当次 hook 的输入文本,**原样保存**,不截断不归一化 |
| `ts` | string | 自动 | UTC ISO 8601,`Z` 结尾 |
| `returned_ids` | string (JSON array) | 是 | 本次新返回的 card_id 列表(已去重过),按相关度排序 |
| `skipped_ids` | string (JSON array) | 是 | 命中但因 dedup 被跳过的 card_id 列表 |

> JSON 数组列存成 TEXT,SQLite 自带 `json_each` / `json_array_length` 处理。**不**抽出成单独的 `recall_event_card` 关联表 —— 那会引入"主表 + 从表"两套写入,又掉回多 source-of-truth 的坑。一个事件对应一组卡的语义本来就是"原子整体",JSON 列正好对齐。

## 存储

### SQLite(唯一存储,无文件镜像)

```sql
CREATE TABLE recall_event (
  event_id      TEXT PRIMARY KEY,
  session_id    TEXT NOT NULL,
  prompt        TEXT NOT NULL,
  ts            TEXT NOT NULL,
  returned_ids  TEXT NOT NULL,           -- JSON array
  skipped_ids   TEXT NOT NULL            -- JSON array
);

CREATE INDEX idx_recall_event_session_ts
  ON recall_event(session_id, ts DESC);
```

**没有文件层镜像**。理由:

- recall 是**会话级短期数据**,不属于"用户的长期记忆"(那是 cards/ reviews/ sessions/)
- hook 调用频率高(每个用户 prompt 一次),多一次磁盘 fsync 不划算
- rebuild 把它清掉是可接受的(reconstruct 不出 prompt,本来也没有"应该重建"的需求)
- 隐私:prompt 是用户输入原文,放 SQLite 一处就好,不要散落到 jsonl 文件给备份系统 / 同步工具不小心拉走

### 事件日志(`events.jsonl`)

**不**写入 `cards/{...}/events.jsonl` 或 `sessions/{...}/events.jsonl`。recall 不是 card 或 session 的"生命周期事件" —— 它不改变 card 的内容、不改变 session 的内容,只是"在某个时刻命中了某张卡"。

(对比:Review 写 `card.events.jsonl` 的 `reviewed` 事件,因为 review 是 card 的状态变化。Recall 不是。)

## 不存在的字段(以及为什么)

| 字段 | 为什么不要 |
|---|---|
| `card_stats.recall_count` | 旧设计有,**新设计 drop**。改成 `SELECT COUNT(*) FROM recall_event, json_each(returned_ids) j WHERE j.value = ?` 现算 —— 一个 join,SQLite 不卡(典型 search 一次拿 ≤20 卡)。换来 single source of truth |
| `recall_event.recall_id` (跟 review_id 命名一致) | 用 `event_id` 而不是 `recall_id`,因为它是 event-shaped 而不是 entity-shaped(没有"读这条 recall 的内容"这种用法,只有"看时间线上发生了什么") |
| `recall_event.top_k` | 不存。top_k 是请求参数,不是事件本质属性。回放时从 `returned_ids` 长度也能推得 |
| `recall_event.embedding_used` 等检索元数据 | 不存。recall 跟 search 的 audit 分两条路径:`search_log` 记 search audit(可回放),`recall_event` 只记 hook 行为(不可回放)。recall 重新跑一次 ≠ 还原历史,因为 embedding model / cards 都可能变 |
| 单独的 `recall_event_card` 关联表 | 见上文 §字段。会引入多表写入,违背 single source of truth |
| `card_id_set` 索引 | 现在不加。`json_each` 反向查"某卡被召了几次"在百卡量级是 ms 级,加 expression index 是过早优化 |

## 写入路径

只一个写入点:`memory.talk recall hook` 服务端处理。**单 INSERT,单事务**:

```python
# service/recall.py — pseudo-code
new_ids = [c.id for c in hits if c.id not in already_recalled(session)]
skipped = [c.id for c in hits if c.id in already_recalled(session)]
if new_ids:
    await db.execute(
        "INSERT INTO recall_event (event_id, session_id, prompt, ts, returned_ids, skipped_ids) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ulid(), sid, prompt, now, json.dumps(new_ids), json.dumps(skipped))
    )
    await db.commit()
```

`bump_recall` 那套**完全删掉**。`card_stats` 里 `recall_count` 这一列也 drop。

### 失败模式

`INSERT` 失败(磁盘满 / 权限) → hook 服务端捕获,**仍然返回正常的 hookSpecificOutput JSON**(契约:hook 永不 exit 非 0)。代价:这次 recall 不去重也不记账,下次 hook 又会把同一批卡再召一遍 —— 可接受,因为去重本来就是"软优化"。

## 读取路径

| 入口 | 查询形态 |
|---|---|
| `recall hook`(去重) | `SELECT DISTINCT j.value FROM recall_event, json_each(returned_ids) j WHERE session_id = ? AND j.value IN (...)` |
| `recall list` | `SELECT session_id, COUNT(*), MAX(ts), SUM(json_array_length(returned_ids)) FROM recall_event GROUP BY session_id ORDER BY MAX(ts) DESC LIMIT ?` |
| `recall read <session_id>` | `SELECT * FROM recall_event WHERE session_id = ? ORDER BY ts [DESC] LIMIT ?` |
| search/read response 里的 `recalls N` | 给一组 card_id,一次 IN 查询拿计数 |

**`recall_event` 不暴露独立 REST 资源** —— 没有 `GET /v3/recall-events/{id}`。它没有"作为对象被检索"的需求,只通过上面 4 个聚合视角访问。

## 跟其它对象的关系

```
RecallEvent
  │
  ├── session_id ──────► Session(可能还没 sync 进 v2,见下)
  │
  ├── returned_ids[] ──► Card(本次新返回的)
  │
  └── skipped_ids[]  ──► Card(命中但被去重的)
```

跟 [Card](talk-card.md) 的关系是**单向引用**:RecallEvent 提到 card_id,但 card 本身**不存反向链** —— card 是否被 recall 过、被 recall 几次,**始终现算**(`COUNT(*) ... FROM recall_event WHERE j.value = card_id`)。

跟 [Session](session.md) 同理:RecallEvent 提到 session_id,但 session 不知道自己产生过 RecallEvent。

### 跟 sync 的时序

recall 是**实时** hook,sync 是**异步定时**。常见时序:

```
[hook 1]  POST /v3/recall {session_id: sess_X, prompt: ...}    ← 写 recall_event(sess_X, ...)
[hook 2]  POST /v3/recall {session_id: sess_X, prompt: ...}    ← 写 recall_event(sess_X, ...)
[hook 3]  POST /v3/recall {session_id: sess_X, prompt: ...}    ← 写 recall_event(sess_X, ...)
[sync]    定时器 → 把 sess_X 落到 sessions/                     ← 现在才有 session 实体
```

所以 RecallEvent 表里**经常出现 sessions 表里还不存在的 session_id**,这是预期行为,不要在写入路径加外键约束 / 不要在 hook 路径查 sessions 表存在性。

等 sync 后落地 sessions,RecallEvent 跟 session 的关联**自然成立**(同 id 互通),不需要 backfill。

## 迁移(0.8.x → 0.9.0)

旧 schema 有 `recall_log(session_id, card_id, recalled_at)` 表 + `card_stats.recall_count` 列。0.9.0 升级时:

1. `DROP TABLE recall_log` —— 不迁移历史。旧表注释明确写 "in-memory-ish — cleared on rebuild",历史本来就是可丢的,且没存 prompt 也补不出 RecallEvent
2. `ALTER TABLE card_stats DROP COLUMN recall_count` —— 改成 derived,旧值丢
3. `CREATE TABLE recall_event ...` + 新索引

升级路径写在 release notes:**recall 历史会清零**,既有 card 的 `recalls N` 数字会从 0 重新累计。语义上跟"从 0 开始记账"等价,用户能理解。

## 不变量(invariants)

1. `recall_event` **append-only**:从不 UPDATE / DELETE(除非 0.9.0 之后再来一次 migration / 显式 rebuild)
2. 同 `(session_id, card_id)` 在所有 RecallEvent 的 `returned_ids` 里**最多出现一次** —— 由 dedup 路径保证(已在 returned 里的下次进 skipped)。**不**靠数据库约束强制,因为约束跨 JSON 列没有合适表达
3. 一个 RecallEvent 的 `returned_ids` 和 `skipped_ids` **不相交**(同一张卡不会同时是 "本次新返回" 和 "本次去重")
4. `prompt` 永远非空字符串(空 prompt 在写入路径就会被拒掉)

## 容量预期

- 一个用户每天写约 100 次 hook(假设积极使用)→ 100 行/天 → ≈ 36k 行/年
- 每行 ~ 200 bytes(prompt 中位数 + 2-3 张卡 ID)→ 7 MB/年
- SQLite + B-tree 索引在 10 万行下查询仍是 ms 级

**不需要分区 / 不需要冷归档**。如果未来真的有几百 GB 量级,加一个 `purge_before(ts)` ops 命令即可,本设计不预留这个能力。
