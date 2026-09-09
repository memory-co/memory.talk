# 向量索引补齐 + EMFILE 恢复

`sessions.indexed_round_count` < `round_count` 表示这个 session 有 round 没被向量化。后台 backfill task 怎么发现、怎么补齐,以及历史上踩过的 LanceDB EMFILE / DashScope 10-batch 坑。

相关:
- Session 写入路径: [session-rounds-write.md](session-rounds-write.md)
- Sync watcher 上下文: [sync-pipeline.md](sync-pipeline.md)

## degraded session 的判定

```sql
indexed_round_count < round_count  →  degraded
```

`round_count` 是该 session 一共有多少 round(append-only 单调增),`indexed_round_count` 是其中有多少已经被 LanceDB rounds 表索引。

差值就是"还没 embed 的 round 数"。差值 > 0 → 该 session 是 degraded,backfill 任务会拣起来重 embed。

## Backfill task

server lifespan 启动时 spin up 一个 backfill task(跟 sync watcher 是独立 task):

```python
async def backfill_loop():
    while True:
        degraded = await db.sessions.list_degraded(limit=10)
        if not degraded:
            await asyncio.sleep(60)
            continue
        for session in degraded:
            try:
                rounds = await load_unindexed_rounds(session)
                vectors = await embedder.embed_batch([r.text for r in rounds])
                await lance.add_rounds(zip_rows(rounds, vectors))
                await db.sessions.bump_indexed_count(session.id, len(rounds))
            except Exception as e:
                await db.sessions.set_last_index_error(session.id, str(e))
                # 不 raise,继续下一个 session
```

- 每 60s 扫一次
- 每轮处理至多 10 个 degraded session
- 单个失败 → 记 `last_index_error`,**不阻塞其他 session 的 backfill**
- 重启 server 即重启 backfill(状态由 SQLite 持久化)

## 0.6.1 DashScope 10-batch 静默截断 bug

历史:

DashScope 的 embedding endpoint 当时(2026-05 报告)有个隐 bug —— 一次 batch 请求里塞 > 10 个 input,服务器会**静默截断**(返回 10 个 embedding,但响应 status 200,没任何 warning)。

代码原本批量调:

```python
batch = rounds[i:i+50]
embeddings = await embedder.embed_batch([r.text for r in batch])
# 期望 len(embeddings) == len(batch),实际 == 10
zip_rows(batch, embeddings)  # 最后 40 行 round 就丢索引了
```

session 看起来 sync 完了,LanceDB rounds 表里却少了 40/50 条。**搜索时这些 round 完全召不回**。

引入 `indexed_round_count` 是这个 bug 的根因修复:每个 session 显式追踪"已索引的 round 数",对不上就 backfill。详见 `docs/report/2026-05-23-search-vector-index-batch-gap.md`。

## EMFILE recovery(0.8.1)

LanceDB 在密集 vector 写入时碰到 macOS launchd `maxfiles=256` 默认 ulimit 会抛 `OSError: [Errno 24] Too many open files`,因为它会保持很多 fragment 文件 open。

处理:

1. catch 这个特定的 OSError
2. log warning 但**不 abort 业务路径** —— session 落 file 已成功,只是 LanceDB 这一步失败
3. 标 `last_index_error="EMFILE"`,等 backfill 任务重试
4. CLI 的 `sync` status 显示 degraded 数量,提示用户 `ulimit -n 4096` 或加 `compact()`

0.8.1 的修复还引入了**定期 compact LanceDB fragments**(降低文件数),从根因减小 EMFILE 触发概率。详见 issue #4。

## 用户视角

`memory.talk sync` 状态输出里的 `index health` 表:

```
## index health

| field | value |
|---|---|
| sessions | 425 |
| rounds | 12735 (all indexed) |
| backfill | `idle` |
```

或者有 degraded session 时:

```
| backfill | `running` · 3 degraded sessions, 47 rounds pending |
```

用户**通常不用做什么** —— backfill task 自己跑完。但如果看到 `last_index_error` 反复出现,需要看 `~/.memory.talk/logs/server.log` 排查上游(embedding provider 是否还活着 / ulimit 够不够)。

## 不会跑去 reindex 已索引的 round

backfill 只补 `indexed_round_count < round_count` 的部分。已经索引过的 round **不重做**,即使 embedding 模型升级了。

要全量重索引必须显式触发(目前是 `rm -rf ~/.memory.talk/vectors && memory.talk server restart`,backfill 会从头开始)。未来计划有 `memory.talk reindex` 子命令统一管理。
