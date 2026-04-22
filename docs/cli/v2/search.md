# search

v2 主检索入口。hybrid FTS + 向量检索 + 元数据 DSL 过滤，结果分两支返回（cards 和 sessions）。每条结果都有一个 `result_id`——这是 v2 里调 `view` 读取 card / session 的唯一合法凭据。

```bash
memory-talk search <query> [--where DSL] [--top-k N]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `<query>` | — | 检索文本。可为空字符串（配合 `--where` 做纯元数据过滤） |
| `--where`, `-w` | 无 | 元数据过滤 DSL（语法同 v1 search） |
| `--top-k` | 10 | 每支（cards / sessions）的上限 |

## 输出

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

注意：
- 返回体里 **不包含裸 `card_id` / `session_id`**。要读内容必须用 `result_id` 调 `view`。
- **links 字段过滤掉已过期的用户 link**——search 里只出现 `ttl >= 0` 的 link（默认 link `ttl = 0` 和活跃用户 link `ttl > 0`）。想看"曾经指过但已过期"的用户 link 要走 `view`。
- search 时 **不续命** link（也不续命对象 TTL）——续命只发生在 `view`。
- `result_id` 形如 `{search_id}.c<rank>` 或 `{search_id}.s<rank>`，`c` / `s` 区分类型；`links[].target_result_id` 形如 `{result_id}.l<N>`，可直接喂给 `view`。
- `rank` 从 1 开始，对齐 `results` 数组位置。

## 追踪语义

每次 search 都会在服务端 `search_log` 表里记录一条（search_id, query, where, created_at）。读取 result_id 时会补记 click（见 `view`）。后续可以基于这两张表分析"这次 search 引导出哪些读取、哪些引用、哪些新建的 card"。

## DSL

支持字段：`session_id`、`card_id`、`tag`、`source`、`created_at`。运算符：`=`、`!=`、`LIKE`、`IN`、`NOT IN`、`AND`。示例：

```bash
memory-talk search "LanceDB" -w 'tag = "decision" AND source = "claude-code"'
memory-talk search "" -w 'created_at > "2026-04-01"'
memory-talk search "bug" -w 'session_id = "abc123"'
```

DSL 解析失败返回 400 错误，带 `DSL parse error` 信息。
