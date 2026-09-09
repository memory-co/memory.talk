# File-canonical 模式

v3 的所有"长生命周期"对象(Card / Review / Session / RecallEvent)都遵循同一套两层存储:

```
file (jsonl / json)     ← canonical · 唯一可信源 · append-only / immutable
SQLite                  ← derived index · 为查询速度存在 · 可丢可重建
```

这份文档说明这套模式的契约 + 写入顺序 + drift 恢复策略。

## 为什么不只 SQLite

- **audit / portability**:server 死、SQLite 文件损坏的灾难情况下,文件层能完整重放对象。SQLite 重建只是建索引,不丢内容。
- **跨工具可读**:`cat ~/.memory.talk/cards/01/card_01.../card.json` 直接看,不需要起服务。备份 = `cp -r`。
- **append-only 易实现**:文件 append + tmp+rename 这两条原语就能保证 immutable 不变量;在 SQLite 里同样的约束要靠多个 trigger + 约定,更脆弱。

## 为什么不只文件

- **查询速度**:从 jsonl 全表扫做 `WHERE session_id = X AND ts > ...` 一次几十 ms,几百次就累垮 hook 路径。
- **多键索引 / JOIN**:跨对象关联(recall_event JOIN cards 拿当前 insight、card_source_cards JOIN cards 看依赖)走 SQL 写得短、跑得快。

所以两层并存:**写双份,读用 SQLite**。

## 各对象的 canonical 位置

| 对象 | Canonical 文件 | SQLite 表 | 备注 |
|---|---|---|---|
| Card payload(insight, rounds, source_cards, created_at) | `cards/<bucket>/<card_id>/card.json` | `cards` | payload immutable;`card.json` 一次写,从不改 |
| Card events(lifecycle) | `cards/<bucket>/<card_id>/events.jsonl` | (无独立表) | append-only |
| Card review mirror | `cards/<bucket>/<card_id>/reviews.jsonl` | (主权 SQLite,文件是镜像) | 例外见下方 § Review |
| Card tags(可变 sidecar) | `cards/<bucket>/<card_id>/tags.json` | `cards.tags` 列 | 跟 payload 解耦,改 tag 不动 card.json |
| Review | `reviews/<bucket>/<review_id>/review.json`(或挂在 card 镜像) | `reviews` | 见 § Review |
| Session meta | `sessions/<source>/<sid[0:2]>/<sid>/meta.json` | `sessions` 行 | sync 写 |
| Session rounds(对话内容) | `sessions/<source>/<sid[0:2]>/<sid>/rounds.jsonl` | LanceDB `rounds` 表(向量化) | append-only |
| Session events | `sessions/<source>/<sid[0:2]>/<sid>/events.jsonl` | (无独立表) | append-only |
| RecallEvent | `sessions/<source>/<sid[0:2]>/<sid>/recall.jsonl` | `recall_event` | append-only |

## 写入合约

**永远 file 先,SQLite 后**。

```python
# 1. 文件层 — 失败立即抛
await storage.write_text(card_doc_key, json.dumps(card))   # 或 append_text 对 jsonl
# (file 失败 → 整体失败,事务回滚)

# 2. SQLite — 失败可降级
try:
    await db.cards.insert(card)
except Exception as e:
    log.warning("SQLite insert failed; file canonical, rebuild will recover: %s", e)
```

**为什么这个顺序**:file 是 canonical。
- SQLite 出问题 → future 的 rebuild 能从 file 完整恢复
- file 出问题 → SQLite 里的索引没有上游可恢复(我们不会从 SQLite 反推 file)

唯一例外是 Review,见下。

## 读取合约

**永远走 SQLite**,文件层只在 rebuild / audit / 用户手动看时被读到。

- Card read → `SELECT FROM cards WHERE card_id = ?` + JOIN stats / source_cards
- Recall list → 在 `recall_event` 上聚合
- Search → LanceDB 命中后用 card_id 反查 SQLite

## Drift 恢复:rebuild 合约

**合约**:每个对象的 SQLite 表都能**完全从文件层重建**。

任意时刻 `DROP TABLE X` + 跑 rebuild → SQLite 内容跟 rebuild 前的文件内容 1:1 对得上。

**实现暂缓**(0.9.x 不交完整 rebuild):
- 真正 drift 是低频事件(磁盘满 / SQLite 损坏 / 跨机迁移)
- rebuild 是 ops 操作,不是日常路径
- 跟"未来一个统一的 `memory.talk rebuild` 命令"配套实现,该命令应该一次性重建所有受影响表

合约先写下来 + 写入路径按"file 先 / SQLite 后 / SQLite 失败可降级"的语义实现,给未来 rebuild 留着力点。

## Review 是例外:SQLite 是主,file 是镜像

[Review](../../structure/v3/review.md) 用反向顺序:SQLite 先 INSERT,然后 `cards/<...>/reviews.jsonl` 追加一行做镜像。

**为什么**:Review 的查询模式(读单张卡的所有 review)跟 card-级聚合天然契合 SQLite,而文件镜像主要服务"备份 / 显式审查",访问频率很低。把 SQLite 当主减少一次额外 IO,而且 review 的 immutability 在 SQLite 行级也能保住。

文件镜像出问题不影响业务 — rebuild 时再从 SQLite 反推就行。

## 为什么 RecallEvent 反过来回到 file-canonical

0.9.0 之前 RecallEvent 一度做成 SQLite-only,理由是"recall 是短期数据,多一次 fsync 不划算"。后来翻回 file-canonical,因为:

1. 之前的核心反对理由("session 还没 sync 进来,path 算不出")在 [session-namespace.md](session-namespace.md) 修好之后已经不成立 —— canonical session_id 在 hook 时就**正确算出来了**,目录路径是确定的,直接写就行
2. cards / reviews / sessions 全部是 file canonical;让 recall 特殊化是反例外
3. 文件层提供 audit / portability —— 服务器死 / SQLite 丢的情况下,recall 历史还在
4. jsonl append 不强制 fsync,实际 IO 成本可忽略
