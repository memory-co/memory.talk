# memory.talk search / sync 索引缺失问题 · 现场报告 v4

- 日期：2026-05-23
- 仓库：`memory.talk`（branch `main`，HEAD `e5248b7`）
- 复现命令：
  ```bash
  memory.talk search "AONE_SANDBOX_ID"
  memory.talk sync --json --limit 20
  ```
- 数据目录：`~/.memory.talk/`
- 结论：**`AONE_SANDBOX_ID` 的最佳匹配不是排序靠后，而是完全没有进入 LanceDB rounds 索引。根因是 DashScope OpenAI-compatible embedding 接口单批最多 10 条 input，而 `IngestService._index_vectors()` 把整个 session 的所有 rounds 一次性提交；超过 10 条会 400，随后 ingest 把向量索引失败当 best-effort 事件吞掉，sync 仍推进 checkpoint 并显示 `errors: 0`。**

---

## 1. 现象

执行：

```bash
memory.talk search "AONE_SANDBOX_ID"
```

返回的 top 10 主要是旧 session 里含 `sandbox_permissions`、`Sandbox API`、`session_id`、`Aone CI` 的噪声片段。真正讨论 `AONE_SANDBOX_ID` 的 session 没出现。

典型返回：

| rank | session | top hit | 说明 |
|---:|---|---:|---|
| 1 | `sess_35de10ad...` | 0.0240 | `sandbox permissions` |
| 2 | `sess_e8680b49...` | 0.0116 | `ABM Sandbox API` |
| 3 | `sess_55273588...` | 0.0296 | `sandbox_permissions` / `session_id` |
| 5 | `sess_ffb3c510...` | 0.0289 | `Aone CI` |

但原始 session 文件里有明确精确匹配：

```text
sess_0a294181-ffc4-4942-8374-8bae539b9e95
idx=24 human
... 当前env中的AONE_SANDBOX_ID下载后放到 /home/node/AONE_SANDBOX_ID ...
```

全量扫描 `~/.memory.talk/sessions/**/rounds.jsonl`：

```text
exact_rounds containing AONE_SANDBOX_ID: 37
main session: sess_0a294181-ffc4-4942-8374-8bae539b9e95
round_count: 525
created_at: 2026-05-21T03:48:52.221Z
synced_at: 2026-05-23T15:02:46Z
```

---

## 2. 关键证据

### 2.1 SQLite / jsonl 有数据，LanceDB 没数据

对目标 session 查 SQLite：

```text
session_id = sess_0a294181-ffc4-4942-8374-8bae539b9e95
source     = claude-code
rounds     = 525
synced_at  = 2026-05-23T15:02:46Z
```

对 LanceDB rounds 表查同一个 `session_id`：

```text
target rows in lance: 0
target exact rows in lance: 0
```

也就是说，search 阶段根本没有机会返回这条最佳记录。

### 2.2 索引整体大量缺失

当前数据规模：

| 存储 | sessions | rounds |
|---|---:|---:|
| SQLite / jsonl | 425 | 12735 |
| LanceDB rounds | 270 | 744 |

更强的模式：

```text
max lance rows per session: 10
indexed sessions with sqlite round_count > 10: 0
```

只要一个 session 超过 10 个 rounds，这次 backfill 就没有任何 rows 成功进入 LanceDB。

### 2.3 embedding endpoint 单批上限就是 10

直接请求当前配置的 DashScope OpenAI-compatible embedding endpoint：

```text
n=10 status=200
n=11 status=400
body={"error":{"message":"<400> InternalError.Algo.InvalidParameter: Value error, batch size is invalid, it should not be larger than 10.: input.contents", ...}}
```

这个上限和 LanceDB 里“每个 session 最多 10 行”的现象完全对齐。

### 2.4 失败事件其实写进了 events.jsonl

目标 session 的事件文件：

```text
~/.memory.talk/sessions/claude-code/0a/sess_0a294181-.../events.jsonl
```

末尾有：

```json
{
  "event": "vector_index_failed",
  "ts": "2026-05-23T15:02:47Z",
  "error": "Client error '400 Bad Request' for url 'https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings' ...",
  "affected_indexes": [1, 2, 3, "...", 525]
}
```

随后仍然写了：

```json
{"event": "imported", "ts": "2026-05-23T15:02:47Z", "added": 525, "round_count": 525}
```

---

## 3. 根因

### 3.1 `_index_vectors()` 没有分批

`memorytalk/service/sessions.py:241-257`：

```python
async def _index_vectors(self, sid: str, source: str, rows: list[dict]) -> None:
    if self.vectors is None or self.embedder is None or not rows:
        return
    try:
        texts = [_embed_input(r["text"] or "") for r in rows]
        vectors = await self.embedder.embed(texts) if texts else []
        lance_rows = [
            {
                "session_id": sid,
                "idx": r["idx"],
                "role": r["role"] or "",
                "text": _segment(r["text"] or ""),
                "vector": v,
            }
            for r, v in zip(rows, vectors)
        ]
        await self.vectors.add_rounds(lance_rows)
```

`rows` 是这次 append 的全部 rounds。冷扫 backfill 首次导入一个历史 session 时，`rows` 经常是几十到几百条。

### 3.2 OpenAI-compatible embedder 也不分批

`memorytalk/provider/embedding.py:65-76`：

```python
async def embed(self, texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            self.endpoint,
            headers={...},
            json={"model": self.model, "input": list(texts), "encoding_format": "float"},
            timeout=self.timeout,
        )
    resp.raise_for_status()
```

当前 endpoint 要求 `input` 长度 `<= 10`，超过就 400。代码没有 chunk，所以整个 session 的向量索引失败。

### 3.3 索引失败被设计为 best-effort

`memorytalk/service/sessions.py:258-266`：

```python
except Exception as e:
    _log.exception("vector index append failed sid=%s", sid)
    await self.events.session_event(
        source, sid, "vector_index_failed",
        error=str(e), affected_indexes=[r["idx"] for r in rows],
    )
```

失败只写事件，不改变 `AppendRoundsResponse.status`。调用方看到的仍是 `status="ok"`。

### 3.4 sync 在 append 成功后推进 checkpoint

`memorytalk/service/sync.py:335-362`：

```python
result, used_offset = await self._send_with_conflict_retry(...)
...
await self.checkpoints.upsert(
    source=adapter.source_name,
    session_id=probe.session_id,
    sha256=probe.sha256,
    last_round_id=new_last,
    line_offset=used_offset,
    updated_at=_ISO(),
)
```

只要 `append_rounds()` 返回 ok，sync 就推进 `(sha256, last_round_id, line_offset)`。之后同一个源文件 sha 命中会直接 skip，不会自动补索引。

---

## 4. 为什么 `memory.talk sync` 看不出异常

执行：

```bash
memory.talk sync --json --limit 20
```

当前输出：

```json
{
  "status": "running",
  "phase": "watching",
  "totals": {
    "discovered": 425,
    "imported": 425,
    "appended": 0,
    "skipped": 0,
    "errors": 0
  },
  "recent": [
    {"session_id": "c31f653c-c046-4772-b6f5-11adf0ec2e94", "event": "imported", "rounds": 35},
    {"session_id": "e9440bff-9bf4-4c3e-abd2-ef2fa10b461c", "event": "imported", "rounds": 94},
    {"session_id": "ded8adff-1e3e-4b33-826f-f856a0c1e20b", "event": "imported", "rounds": 104},
    {"session_id": "b79d27f6-3894-439c-81f1-09ade2dbc3ef", "event": "imported", "rounds": 97}
  ]
}
```

这些 session 实际都发生了 `vector_index_failed`，但 sync status 仍显示全绿。

原因有四层：

1. `SyncWatcher._totals.errors` 只统计 probe / ensure / read_after / append conflict 这类 sync 层异常，不统计 ingest 内部的 best-effort vector failure。
2. `SyncWatcher._record()` 只记录 `imported` / `rounds_appended`，不读取 session `events.jsonl` 里的 `vector_index_failed`。
3. `GET /v3/sync/status` 直接返回 watcher 内存态：`totals` + `recent`，没有做任何索引健康检查。
4. CLI `fmt_sync_status()` 只渲染 API 返回的 `imported/appended/errors/recent`，所以也不会暴露 LanceDB 缺口。

因此 `memory.talk sync` 的“errors: 0”目前只表示“同步 append 没失败”，不表示“可搜索索引完整”。

---

## 5. search 为什么返回噪声

search 的 session 候选只来自 LanceDB：

`memorytalk/service/search.py:278-289`：

```python
hits = await self.vectors.search_rounds(
    query=query, vector=qvec, top_k=top_k * _ROUNDS_OVERSAMPLE,
)
```

LanceDB 缺了所有大 session 后，`AONE_SANDBOX_ID` 的精确匹配不在候选集中。剩下的小 session 里，query 又被 `jieba` 切成：

```text
AONE_SANDBOX_ID => AONE _ SANDBOX _ ID
```

其中 `SANDBOX`、`ID` 都是高频 token，所以会命中：

- `sandbox_permissions`
- `Sandbox API`
- `session_id`
- `Aone CI`

这就是 top 10 看起来“不是最匹配”的直接原因。

---

## 6. 影响范围

只要使用当前 DashScope embedding endpoint，且一次 append 的 rounds 数量超过 10，就会触发：

1. session 写入 SQLite / jsonl 成功；
2. LanceDB rounds 索引整批失败；
3. sync checkpoint 推进；
4. `memory.talk sync` 显示 `imported` 且 `errors: 0`；
5. search 永远搜不到这批 rounds，除非手动 repair/reindex。

当前数据里已经确认：

```text
missing sessions: 155
missing rounds: 12735 - 744 = 11991
```

这不是单个 query 的排序问题，而是索引完整性问题。

---

## 7. 修复建议

### 7.1 立即修：embedding 分批

在 OpenAI-compatible embedder 或 IngestService 层做 chunk，默认每批 10 条：

```python
for chunk in chunks(texts, 10):
    vectors.extend(await embedder.embed(chunk))
```

更稳的方案是给 `EmbeddingConfig` 加 `batch_size`，OpenAI/DashScope 默认 10，local 可更大。

### 7.2 避免整批失败

即使某一批失败，也应该：

- 已成功的批次先写入 LanceDB；
- 失败批次记录具体 `affected_indexes`；
- 不要因为第 11 条触发 400 就让前 10 条也丢掉。

### 7.3 sync status 暴露索引健康

`GET /v3/sync/status` 至少应该包含一段派生索引健康状态：

```json
{
  "index": {
    "sqlite_sessions": 425,
    "sqlite_rounds": 12735,
    "lance_sessions": 270,
    "lance_rounds": 744,
    "missing_sessions": 155,
    "missing_rounds": 11991,
    "vector_index_failed_events": 155
  }
}
```

CLI 文本里也要显示，例如：

```text
| index | degraded: 11991 rounds missing from LanceDB |
| vector_index_failed | 155 sessions |
```

### 7.4 append response 区分“数据写入成功”和“索引成功”

`AppendRoundsResponse` 可以加字段：

```json
{
  "status": "ok",
  "index_status": "failed",
  "index_error": "...",
  "indexed_count": 0,
  "index_failed_count": 525
}
```

sync 收到 `index_status != ok` 时，应该把 `totals.errors` 或新的 `index_errors` 计数抬起来，并把 recent event 显示为 `index_failed` / `imported_with_index_error`。

### 7.5 加 repair/reindex 命令

需要一个从 `rounds.jsonl` 重放 LanceDB 的修复入口：

```bash
memory.talk reindex --sessions
# 或
memory.talk repair-index --source claude-code
```

逻辑：

1. 扫 `~/.memory.talk/sessions/**/rounds.jsonl`；
2. 对每个 session 先 `delete_session_rounds(session_id)`；
3. 按 batch_size=10 重新 embed；
4. 写回 LanceDB；
5. 重建 FTS index。

注意：删除 `~/.memory.talk/sync.db` 不是修复手段。sync 会先 `ensure_session()` 得到 SQLite 里的 `last_round_id`，然后 `read_after(last_round_id)`，旧 rounds 不会重新 append，也不会重新索引。

### 7.6 增加测试

建议补三类测试：

1. OpenAI-compatible embedder batch size 限制：mock endpoint 对 `len(input)>10` 返回 400，断言 ingest 会分批成功。
2. vector index failure 可观测性：mock embedder 抛错，断言 `/v3/sync/status` 不再显示全绿。
3. index coverage health：制造 SQLite 有 3 rounds、LanceDB 缺 1 round，断言 sync/status 或 status API 报 degraded。

---

## 8. 一句话总结

`memory.talk sync` 现在只证明“session append 到文件层/SQLite 成功”，不证明“search 所依赖的 LanceDB 索引成功”。`AONE_SANDBOX_ID` 的最佳记录缺席，是 DashScope 单批 10 条限制 + ingest 不分批 + vector failure 被吞 + checkpoint 推进共同造成的索引缺失。
