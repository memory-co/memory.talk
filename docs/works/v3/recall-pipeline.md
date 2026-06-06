# Recall pipeline

无意识召回(`memory.talk recall hook`)从 hook 触发到数据落地的全流程,加上跨命令派生的视图(`recall list` / `recall read` / search 旁边的 `recalls N` 数字)怎么从同一份数据导出。

相关:
- CLI: [`../../cli/v3/recall.md`](../../cli/v3/recall.md)
- API: [`../../api/v3/recall.md`](../../api/v3/recall.md)
- Schema: [`../../structure/v3/recall.md`](../../structure/v3/recall.md)
- 命名空间细节: [session-namespace.md](session-namespace.md)
- 跟 Review 的角色分工: [forum-dynamics.md](forum-dynamics.md)

## 两层存储 + 单 source of truth

```
sessions/<source>/<sid[0:2]>/<sid>/recall.jsonl   ← canonical · 唯一可信源
                                                    每次 recall hook 追加一行
                                                    含 returned cards 的 insight 快照

recall_event(SQLite 表)                          ← derived index
                                                    从 recall.jsonl 派生,仅为查询速度存在
                                                    所有"事实"以 file 为准;SQLite 可丢可重建
```

详细对比见 [file-canonical-pattern.md](file-canonical-pattern.md)。

## 所有视图怎么导出

| 视图 | 从哪里读 |
|---|---|
| **dedup**(`recall hook` 决定要不要返回某 card) | SQLite: `SELECT DISTINCT j.value FROM recall_event, json_each(returned_ids) j WHERE session_id = ?` |
| **session 列表**(`recall list`) | SQLite: `SELECT session_id, COUNT(*), MAX(ts) FROM recall_event GROUP BY session_id` |
| **session 时间线**(`recall read <session_id>`) | 优先 SQLite(查询快);展示时关联 cards 表拿当前 insight |
| **card 累计召回数**(search/read 结果旁边的 `recalls N`) | SQLite: `SELECT COUNT(*) FROM recall_event, json_each(returned_ids) j WHERE j.value = ?` |
| **audit / restoration**(进程级灾难恢复) | file: `recall.jsonl`,SQLite 重建素材 |

所有 read path 走 SQLite(快),write path 是 **file 先,SQLite 后**(见下方 §写入路径)。

## 写入路径

只一个写入点:`memory.talk recall hook` 服务端。**顺序固定:mkdir → file → SQLite**。

```python
# service/recall.py — pseudo-code
canonical_sid = adapter_for(source).mint_session_id(raw_uuid)
session_dir = data_root / "sessions" / source / canonical_sid[:2] / canonical_sid
session_dir.mkdir(parents=True, exist_ok=True)

event = {
    "event_id": new_ulid(),
    "session_id": canonical_sid,
    "source": source,
    "location": location,
    "ts": utc_now_iso(),
    "prompt": prompt,
    "top_k": top_k,
    "returned": [{"card_id": c.id, "insight": c.insight} for c in new_cards],
    "skipped":  [{"card_id": c.id, "insight": c.insight} for c in skipped_cards],
}

# 1. file first (canonical)
with open(session_dir / "recall.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")

# 2. SQLite index next (best-effort)
try:
    await db.recall.insert_event(...)
except Exception as e:
    log.warning("recall_event SQLite insert failed; file is canonical, "
                "rebuild will recover: %s", e)
```

**为什么 file 必须先写**:file 是 canonical。SQLite 出问题时,future 的 rebuild 路径能从 file 完整恢复;file 出问题时,SQLite 里的索引没有上游可恢复。

### 失败模式

| 阶段 | 失败 | 行为 |
|---|---|---|
| mkdir | 权限 / 磁盘 | 抛 → hook 服务端捕获 → 仍返回空 `hookSpecificOutput` JSON(契约:hook 永不 exit 非 0)→ 这次 recall **完全失败**,不去重不记账 |
| file 写 | 同上 | 同上 |
| SQLite 写 | 磁盘满 / 损坏 | log warning,**file 已经写了 → 这次仍算成功**。`recall hook` 仍返回正常 hookSpecificOutput,只是 SQLite 这条索引行缺失。**SQLite drift 由 rebuild 路径修复** |

### 总是写一条事件

即使 `returned == []`(所有候选都已 dedup'd),仍然写一条 recall_event,只是 returned 为空、skipped 全列。`recall read` 需要这些事件才能展示"这一轮为什么没新东西"。

### 目录可能在 sync 之前就被 recall 创建

hook 时算出 canonical session_id,如果 `sessions/<source>/<sid[0:2]>/<sid>/` 不存在,recall 服务**先创建该目录**(mkdir -p)再追加 `recall.jsonl`。`meta.json` / `rounds.jsonl` 留给 sync 后续来写,不冲突。

详见 [session-namespace.md § sync 时序](session-namespace.md#不验证-session-在-sessions-表里存在)。

## SQLite 重建路径(合约,实现暂缓)

**合约**:SQLite `recall_event` 表的内容**完全可以从 `recall.jsonl` 文件们重建**。任意时刻删 SQLite + 跑 rebuild → SQLite 内容跟 rebuild 前的 file 内容 1:1 对得上。

**实现暂缓**(0.9.x 不交):
- 真正发生 SQLite drift 是低频事件(磁盘满 / 损坏后恢复 / 跨机迁移)
- rebuild 本身是 ops 操作,不是日常 hook 路径
- 跟其它对象(cards / sessions)的 rebuild 命令应该用同一个入口(以后做 `memory.talk rebuild` 时一起加 recall 这一支)

合约先约定下来 + 写入路径按"file 先, SQLite 后, SQLite 失败可降级"的语义实现,留出未来 rebuild 的着力点。

## 派生的 `recall_count`(search/read 旁边)

旧设计有独立的 `card_stats.recall_count` 列,被 recall hook 触发时 `+= 1`。问题:`recall_event` 写入和 `card_stats` UPDATE **不在一个事务里**,进程崩了会**永久 drift 且无人察觉**。

0.9.0 改成**完全派生**:

```sql
-- search/read 展示时 bulk 查一次
SELECT j.value AS card_id, COUNT(*) AS recall_count
FROM recall_event, json_each(recall_event.returned_ids) AS j
WHERE j.value IN (?, ?, ...)
GROUP BY j.value
```

- 没有 `card_stats.recall_count` 列了
- search response 一次拿 ≤20 卡 → 一次 IN 查询 → ms 级
- 单 source of truth,**结构上不可能 drift**

## 不存在的字段(以及为什么)

| 字段 | 为什么不要 |
|---|---|
| `card_stats.recall_count` | 改成现算,见上 |
| `recall_event.recall_id`(跟 review_id 命名一致) | 用 `event_id`,因为它是 event-shaped 而不是 entity-shaped(没有"读这一条 recall 内容"这种用法,只有"看时间线上发生了什么") |
| 单独的 `recall_event_card` 关联表 | 会引入多表写入,违背 single source of truth |
| `card_id_set` 索引 | 现在不加。`json_each` 反向查"某卡被召了几次"在百卡量级是 ms 级,过早优化 |
| `recall_event.embedding_used` 等检索元数据 | recall 不可回放(embedding model / cards 都会变),记录无意义 |

## 不变量

1. **file 是 canonical**;SQLite `recall_event` 是 derived index。两者 drift 时以 file 为准。
2. `recall.jsonl` **append-only**:从不 UPDATE / DELETE(除非显式 rebuild)。
3. `recall_event` SQLite 表理论上也 append-only,但**允许 drift**(写失败 / 跨机迁移),rebuild 时按 file 校对。
4. 同 `(session_id, card_id)` 在所有 RecallEvent 的 `returned` 里**最多出现一次** —— 由 dedup 路径保证。**不**靠数据库约束强制,因为约束跨 JSON 列没有合适表达。
5. 一个 RecallEvent 的 `returned` 和 `skipped` **不相交**。
6. `prompt` 永远非空字符串(空 prompt 在写入路径就会被拒掉)。
7. **写入顺序固定**:mkdir → write recall.jsonl → INSERT recall_event。SQLite 失败不回滚 file(file 是 canonical,符合"宁可前进不可回退"的契约)。

## 容量预期

- 一个用户每天写约 100 次 hook → 100 行/天 → ≈ 36k 行/年
- 每行 ~ 200 bytes(prompt 中位数 + 2-3 张卡 ID)→ 7 MB/年
- SQLite + B-tree 索引在 10 万行下查询仍是 ms 级

**不需要分区 / 不需要冷归档**。如果未来真的有几百 GB 量级,加一个 `purge_before(ts)` ops 命令即可。
