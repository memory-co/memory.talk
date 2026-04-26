# sync

从 Claude Code / Codex 等平台的本地会话文件中发现并导入 session。阻塞执行，结束后一次性返回统计。

```bash
memory-talk sync [--data-root PATH] [--json]
```

参数：
- `--data-root` 可选，指定数据根目录（默认 `~/.memory-talk`）。
- `--json` 输出 JSON 而非默认 text。

行为：
1. 对每个已注册的 adapter（当前为 claude-code）调用 `discover()`，列出平台本地的 session 文件。
2. 对每个文件计算 sha256，和 `ingest_log` 对比——已导入且哈希未变的跳过。
3. 其他文件调 adapter.convert 解析成 session，和已有数据按 **append-only** 策略合并（见下方）。

## ID 规范化

平台原始 session 文件名（例如 Claude Code 给的 UUID `187c6576-875f-4e3e-8fd8-f21fe60190b0`）在写入存储时会被服务端**前缀化为 `sess_`**，即 `sess_187c6576-875f-4e3e-8fd8-f21fe60190b0`。后续所有 v2 命令和 API 里出现的 `session_id` 都是带前缀的形态。`ingest_log` 的主键也是 `sess_*`。

## Append-only 策略

sync 的数据合并只向前追加，不回写已有 round：

- **新文件**：首次导入，完整写入。在 log 里产生一条 `imported` 事件。
- **哈希变了、且 round 数增长**：把多出来的部分当 **新 round** 追加到末尾，`index` 从已有最大 `index + 1` 开始续号。sidechain 情况下也只追加。在 log 里产生一条 `rounds_appended` 事件。
- **哈希变了、但某条已有 round 的内容被改了**（平台覆写了历史对话）：打一条 **warning 到 stderr**（包含 `session_id` + 冲突的 `index`），**跳过这几条**，其它真正新增的 round 照常追加。**不回写已有 round 的存储内容**——card 对这些 index 的引用保持原样，宁可存储和平台"对不齐"也不破坏已有 card。

## 输出

### Text（默认）

```
ok: discovered=42 · imported=3 · skipped=39 · appended=2 · overwrite_warnings=1 · errors=0
```

`errors > 0` 时，每个失败文件的错误已经逐条到 stderr（一行一条）。

### JSON（`--json`）

```json
{
  "status": "ok",
  "discovered": 42,
  "imported": 3,
  "skipped": 39,
  "appended": 2,
  "overwrite_warnings": 1,
  "errors": 0
}
```

字段：
- `imported`：首次导入的 session 数。
- `appended`：触发 `rounds_appended` 的 session 数（哈希变了、纯追加新 round）。
- `overwrite_warnings`：检测到已有 round 被平台覆写、触发告警的 session 数（被跳过的 round 数不体现在 `appended` 里）。
- `errors > 0` 时，失败文件的错误信息逐条打印到 stderr（text 模式行级、JSON 模式 JSON lines）。

导入后新 session 立即可被 `search` 命中；向量侧会在后台异步写入，几秒内生效。

sync **不做索引重建**——只做增量导入。需要重建 FTS / 向量索引时用 [rebuild](rebuild.md)。
