# Embedding API

## POST /v3/embedding/reembed

重算所有 card 的 embedding,覆盖写向量库。**setup wizard 内部调用**(仅在 `embedding.dim` 改变时触发),不直接给最终用户用。

v3 没有独立的 `rebuild` CLI 命令 —— 重算 embedding 嵌在 setup 流程里。这个 HTTP 端点是 setup 跟 server 通讯的内部接口。

### 请求体

```json
{
  "expected_dim": 1024,
  "dry_run": false
}
```

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `expected_dim` | 是 | — | 预期的目标 dim。**安全检查** —— 服务端 reload 后的 `settings.embedding.dim` 必须等于这个值,否则报错。防止 setup 和 server 状态不一致时误清向量 |
| `dry_run` | 否 | `false` | 仅探查:统计要重算的 card 数,不实际跑 |

### 响应:dry_run

```json
{
  "status": "dry_run",
  "cards_total": 184,
  "expected_dim": 1024,
  "current_dim": 1024,
  "vector_index_dim": 384
}
```

`vector_index_dim` 是向量库**实际索引**的维度(可能跟 settings 不一致 —— 那就是要 reembed 的原因)。`current_dim` 是 server reload 后的 settings 值。

### 响应:实际跑

```json
{
  "status": "ok",
  "cards_processed": 184,
  "cards_failed": 0,
  "duration_seconds": 47.2
}
```

阻塞执行,跑完才响应。**整段过程对 search / read 是降级** —— 跑期间向量索引在重建,FTS 路径仍可用,只是 search 命中精度会跌(查得到但语义不太对)。

### 副作用

- 枚举 SQLite `cards` 表所有 card_id
- 对每张 card,从 `card.json` 读 `insight`,过 embedding provider 算新向量,**覆盖**写向量库对应行
- 重算完成后向量索引 dim = `expected_dim`
- **不改 `card.json`**(payload immutable) / 不改 `card_stats` / 不写 events.jsonl
- 跑期间维护一个内存进度计数器(`cards_processed_so_far`),可通过 `GET /v3/status` 看(`status` 临时变为 `reembedding`,带额外字段 —— TODO,目前还没设计这条出口,看实际是否需要)

### 错误

| 情况 | 状态 |
|---|---|
| `expected_dim` 缺失 | 400 |
| `expected_dim` 跟 reload 后的 `settings.embedding.dim` 不一致 | 400, `dim mismatch: expected <N>, settings has <M>` |
| 已有 reembed 在跑 | 409, `reembed already in progress` |
| embedding provider 调用失败(单张 card) | 不中断整体,该 card 记 `cards_failed += 1`,最终响应里报告 |
| embedding provider 完全不可用(连续失败) | 中断,返回 500,响应里 `cards_processed` 是中断前的数 |

### 中断恢复

不支持断点续跑。中断后再次调 `POST /v3/embedding/reembed` 会**从头重算所有 card** —— 这条端点本来就只在 dim 改变时调,大库重算耗时较长但频率极低,不优化这条路径。

### 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| 入口 | `POST /v2/rebuild` —— 重建 FTS / 向量 / 日志全部 | `POST /v3/embedding/reembed` —— **只**重算 embedding |
| 触发方式 | `memory-talk rebuild` CLI | setup 内部调用 |
| 重建范围 | embedding + FTS + 日志重放 | 只 embedding |
| 用户可见命令 | 是 | **否** —— 没有 CLI 命令直接调这个端点 |

v3 把 v2 `rebuild` 拆掉的另外两块怎么办?

- **FTS 索引重建** —— SQLite FTS5 自动维护,不需要手动 rebuild。坏了 → 删 `memory.db` 让 server 启动时从 jsonl 重建(server lifespan 会做这件事,详见 architecture 文档)
- **日志重放** —— `search_log` / `events.jsonl` 是 audit 文件,设计上不存在"重放 SQLite 表"的需求 —— SQLite 表本身已经是真相
