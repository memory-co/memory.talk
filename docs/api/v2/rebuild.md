# Rebuild API

## POST /v2/rebuild

从存储根目录下的源文件（`sessions/`、`cards/`、`logs/*.jsonl`）重建 SQLite 关系表、FTS 索引、向量索引、`search_log`、`event_log`。阻塞执行，跑完一次性返回。

请求体：

```json
{}
```

（当前无参数；保留 JSON body 形式方便后续加 flag）

## 数据来源（jsonl 是真相之源）

v2 把所有"写行为"都落一份 append-only jsonl，SQLite 表是派生索引：

```
~/.memory-talk/
├── sessions/{source}/{id[0:2]}/{session_id}/
│   ├── meta.json
│   └── rounds.jsonl              # session round 追加流
├── cards/{id[0:2]}/{card_id}.json
└── logs/
    ├── search/
    │   └── YYYY-MM-DD.jsonl      # search 请求流，按 UTC 日期切分（→ search_log 表）
    └── events/
        └── YYYY-MM-DD.jsonl      # card created / tag 变更 / link 创建 / sync 事件等（→ event_log 表）
```

每天 UTC 零点滚一次文件。字典序即时间序，rebuild 扫目录按 `sort` 顺序读就是正确的重放顺序。

**没有 `view/` 目录**——v2 不追踪 view 调用（AI 的 tool-use 对话本身是完整的 view 记录，服务端再记一份属于重复）。

retention：`settings.search.search_log_retention_days > 0` 时，rebuild / sync 启动时 `find logs/*/*.jsonl -mtime +N -delete`，按文件级删除，不扫内容。

## 行为

1. 清空 SQLite 关系表、FTS 表、向量表、`search_log` 表、`event_log` 表。
2. 扫描 `sessions/` 和 `cards/`，逐条重新写入关系表 + FTS + 向量。
3. 按时间顺序重放：
   - `logs/search/*.jsonl`（按文件名字典序 = 日期序） → `search_log`
   - `logs/events/*.jsonl`（同上） → `event_log`
4. 返回前 `ensure_fts_index` 强制刷新，确保 rebuild 结束即可立即被 search 命中。

## 响应

```json
{
  "status": "ok",
  "sessions": 12,
  "cards": 47,
  "searches_replayed": 108,
  "events_replayed": 215
}
```

## 对对象 TTL 的影响

rebuild **不改变**对象（card / link）的 `expires_at` 时间戳——那存在对象文件里，不靠事件流重放。已过期的仍然过期，未过期的仍可用。

## 注意

- rebuild 本身是 mechanical 操作——不调 LLM、不重新总结 card。
- 运行期间 API 仍可用，但 search 返回的结果可能是部分重建状态。生产环境建议通过 CLI 的 `server stop` → `rebuild` → `server start`。
- 如果 `logs/*/*.jsonl` 本身丢了，rebuild 只能重建对象，不能重建 search_log / event 流——历史审计就真的没了。建议把 `logs/*/*.jsonl` 纳入常规备份。

## 错误

| 情况 | 状态 |
|------|------|
| 源文件目录不可读 | 500 |
| 重放过程中遇到非法 jsonl 行 | 跳过该行，全部跑完后在响应里返回 `errors_count` |
