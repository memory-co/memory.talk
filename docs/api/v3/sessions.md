# Sessions API

## POST /v3/sessions

**Ingest 专用**。sync watcher 实时把平台本地 session 文件解析后调这个端点写入存储。

v3 里**没有公开的"读 session"接口** —— 读一律走 `POST /v3/search` → `POST /v3/read`。

请求体里的 `session_id` 是**平台原始 id**(例如 Claude Code 的 UUID 文件名)、**不带 `sess_` 前缀** —— 服务端入库时统一前缀化为 `sess_<原始id>`。此后所有 v3 API 出现的 `session_id` 都是带前缀的形态,只有这个 ingest 端点为方便 adapter 直接用平台字段而不强制前缀。

### 请求体

```json
{
  "session_id": "187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "source": "claude-code",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {
    "cwd": "/home/user/myapp",
    "project_id": "187c6576-875f-4e3e-8fd8-f21fe60190b0",
    "model": "claude-opus-4-7"
  },
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "rounds": [
    {
      "round_id": "r001",
      "parent_id": null,
      "timestamp": "2026-04-10T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}],
      "is_sidechain": false,
      "cwd": "/home/user/myapp"
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 平台原始 id,**不带前缀** |
| `source` | 是 | 平台来源(`claude-code` / `codex` / ...) |
| `created_at` | 是 | 第一条 round 时间戳 |
| `metadata` | 否 | 平台扩展;**`metadata.cwd`** 影响 explore namespace 判断 |
| `sha256` | 是 | 平台 session 文件的 hash;sync 增量判断用 |
| `rounds` | 是 | Round 数组 |

`round.index` **由服务端生成,调用方不传** —— 传了被忽略。生成规则见下方。Round / ContentBlock 结构见 [`../../structure/v3/session.md`](../../structure/v3/session.md)。

### Index 续号规则

`index` 是会话内的稳定短编号(从 1 开始,gap-free),是 `POST /v3/cards` 和 `POST /v3/reviews` 引用 round 的键 —— **写入端必须保证它的稳定性**。

1. **首次 ingest**(`session_id` 不存在):按请求体里 `rounds` 数组顺序赋 `1, 2, 3, ...`
2. **追加 ingest**(同 `session_id` 再来,且 `sha256` 变了):
   - 服务端按 `round_id` 对齐
   - **已存且内容未变**:保留原 `index`,**不重新编号**
   - **新增**(请求体有、已存里没):从 `max(existing_index) + 1` 续号
   - **已存但内容被改**(平台覆写):**整条跳过**,原 `index` 仍指向原内容;不参与续号;产生 `rounds_overwrite_skipped` 事件
3. **sidechain round 也占号段**(不为 sidechain 单独编号)
4. **index 一旦分配不再变** —— 这是 card / review 引用安全性的前提

### Append-only 合并策略

| 情况 | 行为 | 事件 |
|---|---|---|
| 首次(`session_id` 不存在) | 完整写入,`index` 从 1 始 | `imported` |
| `sha256` 未变 | 跳过 | 无 |
| `sha256` 变了 + round 数增长 + 已有 round 内容未变 | 多出来的追加,`index` 续号 | `rounds_appended` |
| `sha256` 变了 + 已有 round 内容被覆写 | 这几条**跳过、不回写**;其它真新增照常追加 | `rounds_overwrite_skipped`(detail.indexes 列被跳过的 index) |

**不回写已有 round 的存储内容** —— card / review 对这些 `index` 的引用永远保持原样,宁可存储和平台"对不齐"也不破坏已有引用。

### 响应

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

响应里的 `session_id` 是**已加前缀**的形态 —— 直接喂给 `POST /v3/read` / `POST /v3/reviews`。

| 字段 | 说明 |
|---|---|
| `action` | `imported` / `appended` / `skipped`(hash 未变) / `partial_append`(追加了新 round 且有覆写被跳过) |
| `round_count` | 本次操作后该 session 的总 round 数 |
| `added_count` | 本次追加的 round 数 |
| `overwrite_skipped` | 被跳过的 round `index` 列表(可能为空) |

### 副作用

- 写 / 追加 `sessions/{source}/{id[0:2]}/{session_id}/rounds.jsonl`
- 更新 `meta.json` 和 SQLite `sessions` / `rounds` / `rounds_fts` / `ingest_log` 表
- 向 `events.jsonl` 追加相应事件
- 新 session / 新 round 立即可被 search 命中(FTS 同步写);向量侧异步(若 round 文本进向量),几秒内生效

### 调用方

**仅 sync watcher 内部调用**(详见 [`POST /v3/sync/start`](sync.md))。CLI 不直接打这个端点;外部集成新 adapter 时按这个契约写。

### 错误

| 情况 | 状态 |
|---|---|
| `session_id` 冲突但 `source` 不一致 | 400, `source mismatch` |
| `sha256` 字段缺失 | 400 |
| `rounds` 结构非法 | 400 |
| `rounds[].round_id` 重复 | 400, `duplicate round_id` |

### 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 请求体 | 完全一样,加 `tags` 字段(已废弃) | 同 v2 体,**不接受 `tags`** —— 传了忽略 |
| Index 续号 | 同 | 同 |
| Append-only 策略 | 同 | 同 |
| 响应 | 同 | 同 |
| 调用方 | CLI `sync` 命令(用户手动) | server 内部 watcher(自动持续) |

> 这个端点本身**契约几乎不变** —— 变的是**谁来调** + **以什么频率调**。
