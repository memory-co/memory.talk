# Rebuild API

## POST /v2/rebuild

从存储根目录下的源文件（`sessions/`、`cards/`、`logs/*.jsonl`）重建 SQLite 关系表、FTS 索引、向量索引、`search_log`、view click 表、event log。阻塞执行，跑完一次性返回。

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
    ├── search.jsonl              # search 请求流（→ search_log 表）
    ├── view.jsonl                # view click 流（→ click 表）
    └── events.jsonl              # card created / tag 变更 / link 创建 / sync 事件等（→ event_log 表，对应 /v2/log 查询的事件流）
```

## 行为

1. 清空 SQLite 关系表、FTS 表、向量表、`search_log` / `search_result` 表、`view_link_child` 表、`event_log` / `log_event_ref` 表。
2. 扫描 `sessions/` 和 `cards/`，逐条重新写入关系表 + FTS + 向量。
3. 按时间顺序重放 `logs/search.jsonl`、`logs/view.jsonl`、`logs/events.jsonl`，重建：
   - `search.jsonl` → `search_log` + `search_result`（一次 search 的主行 + 多条 result 行，恢复所有历史 `.c<N>` / `.s<N>` 的语义）
   - `view.jsonl` → view click 表 + `view_link_child`（恢复历史 `.l<N>` 的语义）
   - `events.jsonl` → `event_log` + `log_event_ref`（恢复历史 `.e<N>` 的语义）
4. 返回前 `ensure_fts_index` 强制刷新，确保 rebuild 结束即可立即被 search 命中。

各表的 schema 与字段语义见 [../../structure/v2/search-result.md](../../structure/v2/search-result.md)。

## 响应

```json
{
  "status": "ok",
  "sessions": 12,
  "cards": 47,
  "searches_replayed": 108,
  "views_replayed": 340,
  "events_replayed": 215
}
```

## 对 result_id 的影响

jsonl 里包含每次 search 的 `search_id` + 它产出过的 result_id 条目。rebuild 重放后，**历史 result_id 的 TTL 按原始时间戳计算**：已过期的仍然过期，未过期的仍可用。用户视角看不出 rebuild 发生过。

## 注意

- rebuild 本身是 mechanical 操作——不调 LLM、不重新总结 card。
- 运行期间 API 仍可用，但 search 返回的结果可能是部分重建状态。生产环境建议通过 CLI 的 `server stop` → `rebuild` → `server start` 来做。
- 如果 `logs/*.jsonl` 本身丢了，rebuild 只能重建对象，不能重建 search_log / view 记录 / event 流——历史日志就真的没了。建议把 `logs/*.jsonl` 纳入常规备份。

## 错误

| 情况 | 状态 |
|------|------|
| 源文件目录不可读 | 500 |
| 重放过程中遇到非法 jsonl 行 | 跳过该行，全部跑完后在响应里返回 `errors_count` |
