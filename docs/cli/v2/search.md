# search

v2 主检索入口。hybrid FTS + 向量检索 + 元数据 DSL 过滤，结果分两支返回（cards 和 sessions）。命中的 `card_id` / `session_id` 直接返回给调用方——拿到就能喂给 `view` / `log` / `tag` / `link create`。

```bash
memory-talk search <query> [--where DSL] [--top-k N]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `<query>` | — | 检索文本。可为空字符串（配合 `--where` 做纯元数据过滤） |
| `--where`, `-w` | 无 | 元数据过滤 DSL |
| `--top-k` | `settings.search.default_top_k`（默认 10） | 每支（cards / sessions）的上限 |

## 输出

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
  "cards": {
    "count": 2,
    "results": [
      {
        "card_id": "card_01jz8k2m",
        "rank": 1,
        "score": 0.0312,
        "summary": "选定 LanceDB 做向量存储",
        "snippets": ["...**LanceDB**..."],
        "links": [
          {"link_id": "link_01jzq7rm", "target_id": "sess_f7a3e1", "target_type": "session", "comment": null, "ttl": 0},
          {"link_id": "link_01jzq8sn", "target_id": "card_01jzp3nq", "target_type": "card", "comment": "选型后果", "ttl": 1814400}
        ]
      }
    ]
  },
  "sessions": {
    "count": 1,
    "results": [
      {
        "session_id": "sess_187c6576",
        "rank": 1,
        "score": 0.0289,
        "source": "claude-code",
        "tags": ["decision"],
        "snippets": ["...讨论 **LanceDB** 零依赖..."],
        "links": [
          {"link_id": "link_01jzq9tm", "target_id": "card_01jz8k2m", "target_type": "card", "comment": "从此对话提取", "ttl": 0}
        ]
      }
    ]
  }
}
```

注意：
- 返回体里的 `card_id` / `session_id` / `link_id` 都是**带前缀的裸 id**，直接喂给 `view` / `log` / `link create` 即可，不需要任何中间转换。
- `search_id` 是本次查询的**审计 id**——只出现在服务端 `search_log` 表和 `log` 命令的 detail 里，**不用于任何后续读取**。
- `links` 过滤掉**已过期的用户 link**（`ttl < 0`）——只保留 `ttl >= 0`（默认 link + 活跃用户 link）。想看过期 link 走 `view`。
- search 本身**不续命**任何对象或 link——续命只发生在 `view`。
- `rank` 从 1 开始，对齐 `results` 数组位置。

## 追踪语义

每次 search 都会在服务端 `search_log` 表里记录一条（`search_id`, `query`, `where`, `created_at`, `card_hits`, `session_hits`）。这是**纯审计**——不做"凭据发行"，不参与任何后续调用的校验。

想看"这次 AI 会话用了哪些数据"——看 AI 自己的 tool-use 对话记录（sync 之后存成一个 session），那里有每次 `view` / `search` 的输入输出原文。服务端不再造重复的追踪层。

search_log 默认永久保留。老化策略见 `settings.search.search_log_retention_days`。

## DSL

支持字段：`session_id`、`card_id`、`tag`、`source`、`created_at`。运算符：`=`、`!=`、`LIKE`、`IN`、`NOT IN`、`AND`。示例：

```bash
memory-talk search "LanceDB" -w 'tag = "decision" AND source = "claude-code"'
memory-talk search "" -w 'created_at > "2026-04-01"'
memory-talk search "bug" -w 'session_id = "sess_abc123"'
```

DSL 解析失败返回 400 错误，带 `DSL parse error` 信息。

search 输入 / 输出 / 落库结构的完整定义见 [search-result.md](../../structure/v2/search-result.md)。
