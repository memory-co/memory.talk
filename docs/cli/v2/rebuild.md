# rebuild

从存储根目录下的源文件（`sessions/`、`cards/`、以及 `logs/*.jsonl`）重建 SQLite 行、FTS 索引、向量索引、`search_log`、`event_log`。阻塞执行，跑完一次性返回。

```bash
memory-talk rebuild [--json]
```

适用场景：
- SQLite 或 LanceDB 损坏 / 丢失
- 切换了 embedding provider，想让已有 card 重新计算向量
- 调整了 FTS tokenizer 参数

## 数据来源（jsonl 是真相之源）

v2 把**所有"写行为"都落一份 append-only jsonl**，SQLite 表是派生索引：

```
~/.memory-talk/
├── sessions/{source}/{id[0:2]}/{session_id}/
│   ├── meta.json
│   └── rounds.jsonl                  # session round 追加流
├── cards/{id[0:2]}/{card_id}.json    # card 静态文件
└── logs/
    ├── search/
    │   └── YYYY-MM-DD.jsonl          # search 请求流，按 UTC 日期切分（每日一个文件）
    └── events/
        └── YYYY-MM-DD.jsonl          # card 创建 / tag 变更 / link 创建 / sync 事件等，同样按 UTC 日期切分
```

每天 UTC 零点滚一次文件。字典序即时间序（`2026-04-20 < 2026-04-21`），rebuild 扫目录按 `sort` 顺序读就是正确的重放顺序。

**没有 `view/` 目录**——v2 不追踪 view 调用（AI 的 tool-use 对话本身是完整的 view 记录，服务端再记一份属于重复）。

retention：`settings.search.search_log_retention_days > 0` 时，rebuild / sync 启动时 `find logs/*/*.jsonl -mtime +N -delete`，按文件级删除，不扫内容。

## 行为

1. 清空 SQLite 关系表、FTS 表、向量表、`search_log` 表、`event_log` 表。
2. 扫描 `sessions/` 和 `cards/` 下所有文件，逐条重新写入关系表 + FTS + 向量。
3. 按时间顺序重放：
   - `logs/search/*.jsonl`（按文件名字典序 = 日期序） → `search_log`
   - `logs/events/*.jsonl`（同上） → `event_log`
4. 返回前 `ensure_fts_index` 强制刷新，确保 rebuild 结束即可立即被 search 命中。

## 输出

### Text（默认）

```
ok: sessions=12 · cards=47 · searches_replayed=108 · events_replayed=215 · errors=0
```

### JSON（`--json`）

```json
{
  "status": "ok",
  "sessions": 12,
  "cards": 47,
  "searches_replayed": 108,
  "events_replayed": 215,
  "errors_count": 0
}
```

## 注意

- rebuild 本身是 mechanical 操作——不调 LLM、不重新总结 card。
- rebuild 期间 server 进入 `rebuilding` 状态，所有非 `/v2/status` 的请求都会被 503 拦掉（详见 server 中间件）。客户端调用此命令期间应避免并发其它写。
- 如果 jsonl 日志文件本身丢了，rebuild 只能重建对象，不能重建 search_log / event 流——历史审计就真的没了。建议把 `logs/*/*.jsonl` 纳入常规备份。
- **对象的 `ttl` / `expires_at` 靠对象文件里的存储状态**——不是从事件流重放出来的。rebuild 不会改变 card / link 的过期状态。
