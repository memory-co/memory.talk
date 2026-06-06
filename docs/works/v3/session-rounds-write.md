# Session rounds 写入

`sessions.rounds[]` 是 append-only + index 单调递增 + LanceDB 同步索引的三重契约。这份文档讲为什么这三条凑到一起 + 写入路径细节。

相关:
- Session schema: [`../../structure/v3/session.md`](../../structure/v3/session.md)
- Sync 视角(谁触发这条路径): [sync-pipeline.md](sync-pipeline.md)
- 向量索引补齐: [index-backfill.md](index-backfill.md)

## 三层存储

```
sessions/<source>/<id[0:2]>/<sid>/rounds.jsonl   ← canonical · append-only · 每行一个 round
                                                   index 由 ingest 服务赋值,单调递增 gap-free

sessions 表(SQLite)                              ← 元数据 + 游标
                                                   round_count / last_round_id
                                                   不存 round 内容

LanceDB rounds 表                                 ← FTS + 向量索引
                                                   {session_id, idx, role, text, vector}
                                                   FTS over text + cosine over vector
                                                   indexed_round_count 追踪进度
```

## Index 续号规则

`index` 是会话内的稳定短编号,**是 card / review 引用 round 的键**,因此写入端必须保证它的稳定性。

1. **首次 ingest**(session 不存在):按 `append_rounds` 请求里 `rounds[]` 数组顺序赋 `1, 2, 3, ...`
2. **追加 ingest**(`append_rounds(expected_prev_round_id=X)`,X 匹配 server 的 `last_round_id`):
   - 新增的 rounds **整体追加到末尾**,`index` 从 `max(existing_index) + 1` 续号
   - **不做 round_id 级别的 diff** —— sync 已经基于游标算好"哪些是新的",ingest 直接 append
3. **冲突**(`expected_prev_round_id` ≠ server 实际 `last_round_id`):返回 `status=conflict`,**不写任何 round**;sync 负责重读 + 重试(详见 [sync-pipeline.md](sync-pipeline.md))
4. **sidechain round 也占号段** —— 不为 sidechain 单独编号
5. **index 一旦分配就不再变** —— card / review 引用安全性的前提

## 为什么 strictly append-only

v3 是 strictly append-only:**同一个 `round_id` 内容被改了,这个事件根本不会到达 server**(sync 的 `read_after` 只产生 strictly-new round)。即使到达,server 端的 UNIQUE 约束 + `INSERT OR IGNORE` 会把它当重复行忽略,不会覆写已有内容。

理由:

1. **下游引用稳定性**:card 引用 round 是 `{session_id, index}`。改 round 内容 = 改 card 的事实证据,可能让 card 自相矛盾,不可接受。
2. **审计**:`events.jsonl` 是历史,改了就不真实。
3. **简化重放**:append-only + UNIQUE 让 ingest 是天然幂等的 —— 失败重试不会双写。

## 写入路径

```python
# IngestService.append_rounds — pseudo-code
async def append_rounds(req):
    actual_prev = (await db.sessions.get(req.session_id))["last_round_id"]
    if actual_prev != req.expected_prev_round_id:
        return {"status": "conflict", "actual_prev_round_id": actual_prev}

    # 1. 文件层 append(canonical)
    for r in req.rounds:
        r["index"] = next_index  # 1 起,单调递增
        await storage.append_text(rounds_key, json.dumps(r) + "\n")
        next_index += 1

    # 2. SQLite 元数据 update
    await db.sessions.update_cursor(
        session_id=req.session_id,
        round_count=new_count,
        last_round_id=req.rounds[-1].round_id,
        synced_at=utc_now,
    )

    # 3. LanceDB rounds 索引(best-effort)
    try:
        embeddings = await embedder.embed_batch([r["text"] for r in req.rounds])
        await vectors.add_rounds([
            {"session_id": sid, "idx": r["index"], "role": r["role"],
             "text": _segment(r["text"]), "vector": emb}
            for r, emb in zip(req.rounds, embeddings)
        ])
        await db.sessions.bump_indexed_count(sid, len(req.rounds))
    except Exception as e:
        log.warning("LanceDB index failed for %s: %s; backfill will retry", sid, e)
        await db.sessions.set_last_index_error(sid, str(e))

    return {"status": "ok", "last_round_id": last_round.round_id}
```

- file 写失败 → 整体失败,返 500,sessions 表也不 update
- LanceDB 失败 → 仅记 `last_index_error` + 让 `indexed_round_count < round_count`,**业务仍算成功**(rounds 已经 in file + SQLite)
- backfill 路径会捡起 degraded 的 session 重新 embed

详见 [index-backfill.md](index-backfill.md)。

## ContentBlock

Round 的 `content` 是 ContentBlock 数组:

| type | 字段 | 说明 |
|---|---|---|
| `text` | `text` | 文本内容 |
| `code` | `language`, `text` | 代码块 |
| `thinking` | `thinking` | AI 思考过程 |

工具调用(Claude Code 的 `tool_use` / `tool_result`)按 adapter 的映射规则展开成两条独立 round,详见 v2 [session.md](../../structure/v2/session.md#工具调用场景) —— 这部分 v3 沿用 v2 映射约定。

## LanceDB 里 round 是怎么存的

```
rounds table:
  session_id: TEXT     (sess-...)
  idx:        INT      (1-based, 跟 file 一致)
  role:       TEXT
  text:       TEXT     (FTS 索引)
  vector:     ARRAY    (cosine 索引)
```

`text` 在写入前先过一次 segmentation(中文分词等),让 FTS 在 token 级别可命中。这是 LanceStore 内部细节,业务层不感知。

搜索时 LanceDB hybrid:`text` 上 FTS + `vector` 上 cosine,RRF 合并(详见 [search-ranking.md](search-ranking.md))。
