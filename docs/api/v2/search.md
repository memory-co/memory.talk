# Search API

## POST /v2/search

v2 主检索入口。hybrid FTS + 向量检索 + 元数据 DSL 过滤。返回两支结果（`cards` 和 `sessions`），每条带 `result_id`——后续读取、打 tag、建 link 的唯一凭据。

请求体：

```json
{
  "query": "LanceDB 选型",
  "where": "tag = \"decision\" AND source = \"claude-code\"",
  "top_k": 10
}
```

| 字段 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `query` | 是 | — | 检索文本。可为空字符串（配合 `where` 做纯元数据过滤） |
| `where` | 否 | 无 | 元数据过滤 DSL。支持字段：`session_id`、`card_id`、`tag`、`source`、`created_at`。运算符：`=`、`!=`、`LIKE`、`IN`、`NOT IN`、`AND` |
| `top_k` | 否 | 10 | 每支（cards / sessions）的上限 |

响应：

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
  "cards": {
    "count": 2,
    "results": [
      {
        "result_id": "sch_01K7XABC....c1",
        "rank": 1,
        "score": 0.0312,
        "summary": "选定 LanceDB 做向量存储",
        "snippets": ["...**LanceDB**..."],
        "links": [
          {"target_result_id": "sch_01K7XABC....c1.l1", "target_type": "session", "comment": null, "ttl": 0},
          {"target_result_id": "sch_01K7XABC....c1.l2", "target_type": "card", "comment": "选型后果", "ttl": 1814400}
        ]
      }
    ]
  },
  "sessions": {
    "count": 1,
    "results": [
      {
        "result_id": "sch_01K7XABC....s1",
        "rank": 1,
        "score": 0.0289,
        "source": "claude-code",
        "tags": ["decision"],
        "snippets": ["...讨论 **LanceDB** 零依赖..."],
        "links": [
          {"target_result_id": "sch_01K7XABC....s1.l1", "target_type": "card", "comment": "从此对话提取", "ttl": 0}
        ]
      }
    ]
  }
}
```

## 返回体规则

- **不包含裸 `card_id` / `session_id`**。读对象一律用 `result_id` 调 `POST /v2/view`。
- `links` 里**过滤掉已过期的用户 link**（`ttl < 0`）——只出现 `ttl >= 0` 的 link（`ttl = 0` 默认 link + `ttl > 0` 活跃用户 link）。想看过期 link 要走 `/v2/view`。
- **search 不续命**任何对象或 link——续命只发生在 `/v2/view`。
- `result_id` 形如 `{search_id}.c<rank>` 或 `{search_id}.s<rank>`；`links[].target_result_id` 形如 `{result_id}.l<N>`。
- `rank` 从 1 开始，对齐 `results` 数组位置。

## 副作用

在服务端 `search_log` 表（以及 `logs/search.jsonl`）追加一条 `(search_id, query, where, created_at)`。每条 result 在读取时补记 click（见 [view.md](view.md)）。

## 错误

| 情况 | 状态 |
|------|------|
| `where` DSL 解析失败 | 400，`DSL parse error: <details>` |
| `top_k` 超过 settings 上限 | 400 |
