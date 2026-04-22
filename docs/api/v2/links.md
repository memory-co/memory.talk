# Links API

v2 里 link API **只有 create**，专门写"用户 link"（`ttl > 0`，可被 `/v2/view` 续命，独立过期）。查询 / 删除都不开放——link 的存在随 `/v2/view` 的响应返回（嵌在 `links` 字段里），TTL 随读取隐式刷新。

"默认 link"（`ttl = 0`，card 写入时自动生成的 card→session）**不走这个接口**——它随 `/v2/cards` 副产生，调用方不传、不参与。

## POST /v2/links

请求体：

```json
{
  "source_id": "card_01jz8k2m",
  "source_type": "card",
  "target_id": "sess_187c6576",
  "target_type": "session",
  "comment": "选型之后踩的坑"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `source_id` | 是 | 源对象带前缀 id（`card_<...>` 或 `sess_<...>`） |
| `source_type` | 是 | `card` 或 `session`。必须和 `source_id` 前缀一致，否则 400 |
| `target_id` | 是 | 目标对象带前缀 id |
| `target_type` | 是 | `card` 或 `session`。必须和 `target_id` 前缀一致 |
| `comment` | 否 | 说明为什么关联，长度上限 `settings.search.comment_max_length` |

支持的类型组合（方向由 source → target 表达，双向都允许）：

| source | target |
|--------|--------|
| card | card |
| card | session |
| session | card |
| session | session |

禁止 `source_id == target_id`（自环）。

## 响应

```json
{"status": "ok", "link_id": "link_01jzq7rm", "ttl": 1209600}
```

- `ttl` = 写入时刻的 `settings.ttl.link.initial`（默认 1209600 秒 = 14 天）。
- 返回的 `link_id` **不用于**后续读取或删除——v2 不暴露这类管理路径。主要用于日志 / 调试定位。

## 副作用

- 在 SQLite link 表 + `logs/events.jsonl` 里各落一条。
- 两端对象的 log 都追加一条 `linked` 事件（`direction: incoming/outgoing` 各一）。
- 不改变两端对象自己的 TTL。

## 错误

| 情况 | 状态 |
|------|------|
| `source_id` / `target_id` 前缀不是 `card_` / `sess_` | 400，`invalid id prefix` |
| `source_type` / `target_type` 和 id 前缀不一致 | 400，`type mismatch` |
| 对象不存在 | 404 |
| `source_id == target_id`（自环） | 400，`self-loop not allowed` |
| `comment` 超长 | 400，`comment too long` |
