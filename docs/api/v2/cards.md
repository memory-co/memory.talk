# Cards API

## POST /v2/cards

创建一张 Talk-Card。自动计算 summary embedding、写入向量库，并为 `rounds` 里出现过的每个 session 自动生成一条默认 link（`ttl = 0`）。

v2 里 card API **只有写**。要再读取，调 `/v2/view` 即可（`card_id` 就是合法 id，不需要中间转换）。

请求体：

```json
{
  "summary": "选定 LanceDB 做向量存储",
  "rounds": [
    {"session_id": "sess_abc123", "indexes": "11-15"},
    {"session_id": "sess_def456", "indexes": "3,7,12"}
  ],
  "card_id": "card_01jz8k2m",
  "from_search_id": "sch_01K7XABC..."
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `summary` | 是 | 一句话认知总结，也是 embedding 锚点 |
| `rounds` | 是 | 引用列表，每项 `{session_id, indexes}`。`session_id` 必须是 `sess_<...>`。服务端按 `session.rounds[].index` 展开。可为空数组（合成 card） |
| `card_id` | 否 | 不提供则自动生成 `card_<ULID>`。传入时必须是 `card_<...>` 形态 |
| `from_search_id` | 否 | 如果此 card 基于某次 search 结果提炼，带上那次 search 的 `search_id`。服务端落 log 的 `created` 事件时回填 |

**请求体里没有 `links`**——card → session 的默认 link 基于 `rounds` 出现过的 `session_id` 自动生成（每个不同 session_id 一条，`comment` 为 null，`ttl = 0`）。想补额外关联用 `POST /v2/links`。

## indexes 语法

| 形式 | 示例 | 含义 |
|------|------|------|
| 区间 | `"11-15"` | 闭区间 `[11, 15]`，展开为 `11,12,13,14,15` |
| 列表 | `"3,7,12"` | 离散的 index 列表 |

约束（不满足即拒绝整次写入）：
- **严格单调递增**——否则 400，`indexes must be monotonically increasing`。
- **越界或 session 不存在**——400，`index N out of range for session <session_id>`。
- 同一个 `session_id` 允许多次出现（跳过中间段）；不同 item 之间无顺序约束。

## 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m"}
```

返回的 `card_id` 就是**以后所有地方用的读取凭据**——直接喂给 `/v2/view` / `/v2/log` / `/v2/links` 即可。

## 副作用

- 校验并展开 `rounds`：失败则整次不落库。
- 展开后每条 round 存为 `{role, text, session_id, index}`——`session_id` 和 `index` 不进向量索引。
- 为每个不同的 `session_id` 自动生成一条 card → session 默认 link（`ttl = 0`）。
- 自动计算 `summary` 的 embedding，写入向量库。
- 向 `logs/events.jsonl` 追加 card 的 `created` 事件和涉及到的 session 的 `card_extracted` 事件（同 session 合并）。

## 错误

| 情况 | 状态 |
|------|------|
| `summary` 为空 | 400 |
| `rounds` 非数组 / 项格式错误 | 400 |
| `rounds[].session_id` 不以 `sess_` 开头 | 400，`invalid session_id prefix` |
| `card_id` 传入但不以 `card_` 开头 | 400，`invalid card_id prefix` |
| `indexes` 非单调递增 | 400，`indexes must be monotonically increasing` |
| index 越界或 session 不存在 | 400，`index N out of range for session <session_id>` |
| `card_id` 冲突 | 409，`card_id already exists` |
