# Sessions API

## POST /v2/sessions

**Ingest 专用**。CLI `sync` 调这个端点把平台本地文件解析出的 session 写入存储。**v2 里没有公开的 "读 session" 接口**——读一律经 `/v2/search` → `/v2/view`。

请求体里的 `session_id` 是**平台原始 id**（例如 Claude Code 的 UUID 文件名），**不带 `sess_` 前缀**——服务端入库时统一前缀化为 `sess_<原始id>`。此后所有 v2 API 里出现的 `session_id` 都是带前缀的形态，只有这个 ingest 端点为了方便 adapter 直接用平台字段而不强制前缀。

请求体：

```json
{
  "session_id": "187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "source": "claude-code",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {"project": "/home/user/myapp"},
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "rounds": [
    {
      "round_id": "r001",
      "parent_id": null,
      "timestamp": "2026-04-10T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}],
      "is_sidechain": false
    }
  ]
}
```

`index` 字段**由服务端生成，调用方不传**——传了会被忽略。生成规则见下方"Index 续号规则"。

Round 和 ContentBlock 结构见 [session.md](../../structure/v2/session.md)。

## Index 续号规则

`index` 是会话内的稳定短编号（从 1 开始，gap-free），是 `POST /v2/cards` 引用 round 的键，因此**写入端必须保证它的稳定性**。规则：

1. **首次 ingest（`session_id` 不存在）**：按请求体里 `rounds` 数组顺序，依次赋 `1, 2, 3, ...`。
2. **追加 ingest（同 `session_id` 再来一次、且 `sha256` 变了）**：
   - 服务端先把请求体里的 rounds 和已存的 rounds 按 `round_id` 对齐。
   - **已存且内容未变的 round**：保留原 `index`，**不重新编号**。
   - **新增的 round**（请求体里有、已存里没有）：按它们在请求体里的相对顺序，从 `max(existing_index) + 1` 开始续号。
   - **已存但内容被改的 round**（覆写）：**整条跳过**，原 `index` 仍指向原内容；不参与续号；产生 `rounds_overwrite_skipped` 事件（见 [log.md](log.md)）。
3. **sidechain round 也占号段**——不为 sidechain 单独开一套编号，统一按数组出现顺序续号。
4. **index 一旦分配就不再变动**——session 的所有历史 round `index` 在生命周期内保持稳定。这是 card 引用安全性的前提：card 落库时存的 `{session_id, index}` 永远指向写入时刻看到的那条 round。

### 例子

session `abc123` 已有 20 条 round，`index` 1-20。下次 sync 平台文件多了 5 条新对话，但其中第 15 条的 `text` 被平台编辑过：

| 新请求体里第 N 条 | 命中已存的 round | 服务端动作 | 最终 index |
|------------------|-----------------|-----------|-----------|
| 1-14 | 是（内容一致） | 跳过，保留原 index | 1-14 |
| 15 | 是（**内容变了**） | **跳过**，原 index 仍指向原内容；产生 `rounds_overwrite_skipped` | 15（仍指原内容） |
| 16-20 | 是（内容一致） | 跳过，保留原 index | 16-20 |
| 21-25 | 否（新增） | 追加，依次赋 21、22、23、24、25 | 21-25 |

响应里 `action = "partial_append"`、`added_count = 5`、`overwrite_skipped = [15]`。



## Append-only 合并策略

同一 `session_id` 可以多次 ingest。服务端按 **append-only** 合并：

| 情况 | 行为 | 产生的事件 |
|------|------|-----------|
| 首次（`session_id` 不存在） | 完整写入，`index` 从 1 开始 | `imported` |
| `sha256` 未变 | 跳过 | 无 |
| `sha256` 变了、round 数增长、已有 round 内容未变 | 只把多出来的当新 round 追加到末尾，`index` 从已有最大 `index + 1` 续号 | `rounds_appended` |
| `sha256` 变了、检测到某条已有 round 的内容被覆写 | 这几条 **被跳过**、不回写；其它真正新增的 round 照常追加 | `rounds_overwrite_skipped`（按 session 粒度一条事件，`detail.indexes` 列被跳过的 index） |

**不回写已有 round 的存储内容**——card 对这些 `index` 的引用永远保持原样，宁可存储和平台"对不齐"也不破坏已有 card。

## 响应

```json
{
  "status": "ok",
  "session_id": "sess_187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "action": "imported",
  "round_count": 20,
  "added_count": 0,
  "overwrite_skipped": []
}
```

响应里的 `session_id` 是**已加前缀的形态**——这就是将来喂给 `/v2/view` / `/v2/log` / `/v2/tags/*` 的合法 id。

| 字段 | 说明 |
|------|------|
| `action` | `imported` / `appended` / `skipped`（hash 未变） / `partial_append`（追加了新 round，且有覆写被跳过） |
| `round_count` | 本次操作之后该 session 的总 round 数 |
| `added_count` | 本次追加的 round 数 |
| `overwrite_skipped` | 被跳过的 round `index` 列表，可能为空 |

## 副作用

- 写 / 追加 `sessions/{source}/{id[0:2]}/{session_id}/rounds.jsonl`。
- 更新 `meta.json`、`ingest_log`（含 `sha256`）。
- 向 `logs/events/<今日 UTC 日期>.jsonl` 追加相应事件。
- 新 session / 新 round 立即可被 search 命中（FTS 同步写）；向量侧异步写入，几秒内生效。

## 错误

| 情况 | 状态 |
|------|------|
| `session_id` 冲突但 `source` 不一致 | 400，`source mismatch` |
| `sha256` 字段缺失 | 400 |
| round 结构非法 | 400 |

## 为什么只是 ingest 而不是 "sessions API"

- v2 读路径统一经 search→view，没有 `GET /v2/sessions/:id`。
- CLI 的 `sync` 不调用任何读端点——它只读平台本地文件和 `ingest_log`（服务端内部状态），然后 POST 这里。
