# Links API

v2 里 link API **只有 create**，专门写"用户 link"（`ttl > 0`，可被 `/v2/view` 续命，独立过期）。查询 / 删除都不开放——link 的存在随 `/v2/view` 的响应返回（嵌在 `links` 字段里），TTL 随读取隐式刷新。

"默认 link"（`ttl = 0`，card 写入时自动生成的 card→session）**不走这个接口**——它随 `/v2/cards` 副产生，调用者不传、不参与。

## POST /v2/links

请求体：

```json
{
  "source": "sch_01K7XABC....c1",
  "target": "sch_01K7XABC....s2",
  "comment": "选型之后踩的坑"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `source` | 是 | result_id |
| `target` | 是 | result_id |
| `comment` | 否 | 说明为什么关联 |

**`source` / `target` 只接受 `result_id`**——裸 `card_id` / `session_id` 一律拒绝。必须先 `/v2/search` 拿到结果，再在它们之间建 link。这是刻意设计：v2 里"引用一个对象"永远要经过 search 走一遭，服务端借此追踪 link 从何而来。

可接受的 result_id 形态：`.c<N>`（card）、`.s<N>`（session），以及 view 响应里现生的 `.l<N>`、log 响应里的 `.e<N>`（继续追对端）。

支持的类型组合（方向由 source → target 表达，双向都允许）：

| source | target |
|--------|--------|
| card | card |
| card | session |
| session | card |
| session | session |

禁止 `source == target`（自环，两个 result_id 解析到同一个对象时也算）。

## 响应

```json
{"status": "ok", "link_id": "01jzq7rm...", "ttl": 1209600}
```

- `ttl` = settings 里的用户 link 初始值（默认 100）。
- 返回的 `link_id` **不用于**后续读取或删除——v2 不暴露这类管理路径。它保留只是为了日志 / 调试里定位。

## 副作用

- 在 SQLite link 表 + `logs/events.jsonl` 里各落一条。
- 两端对象的 log 都追加一条 `linked` 事件（`direction: incoming/outgoing` 各一）。
- 不改变两端对象自己的 TTL。

## 错误

| 情况 | 状态 |
|------|------|
| `source` 或 `target` 不是 result_id（裸 `card:xxx` / `session:xxx` 或其它前缀） | 400，`source/target must be a result_id` |
| result_id 已过期 | 410，`expired` |
| result_id 未知 / 无法解析 | 404 |
| `.l<N>` 指向的底层 link 已过期 | 410，`expired` |
| `source` 和 `target` 解析到同一个对象 | 400，`self-loop not allowed` |
| 类型组合不在支持表内 | 400，`unsupported link type: <source_type> -> <target_type>` |
| `comment` 超长（见 settings 上限） | 400，`comment too long` |
