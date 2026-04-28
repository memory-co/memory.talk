# test_search_plain_query

`memory-talk search <query>` —— 不带 DSL 过滤的普通关键词检索场景。

## 关注点

**CLI → httpx → FastAPI → SearchService → LanceDB → 响应体**的全链路是否跑通,
以及响应的**结构契约**是否符合 `SearchResponse` schema。

**不测试**的:
- 排序 / 相关性质量(哪个 hit 在第几名、score 多少)
- Snippet 高亮的具体形态
- jieba 分词对检索结果的精度影响
- RRF reranker 参数调优

上面那些由**独立的搜索质量测试层**(未来另外加)覆盖。这里的 CLI 测试只验证
"命令能跑、响应字段齐、副作用(search_log)正常"。

## 场景

| 测试函数 | 验证什么 |
|---|---|
| `test_search_returns_structured_response` | search_id 前缀 `sch_`、`query` 回显、cards/sessions 两个 bucket 各自有 `count` 和 `results`,并且 `count == len(results)` |
| `test_search_finds_the_matching_card` | query="LanceDB" 至少能找到一张 summary 含 "LanceDB" 的 card;每条 hit 有契约规定的所有字段(card_id/rank/score/summary/snippets/links) |
| `test_search_persists_search_log` | 一次 CLI 调用对应一条 `search_log` 行(副作用落库) |
| `test_search_respects_top_k` | `--top-k 1` 让每桶 count ≤ 1 |

## 种子数据

- 2 个 session:
  - `sess_platform-db`:文本 "we picked LanceDB for vector storage"
  - `sess_platform-bug`:文本 "fixed a jsonl parser bug yesterday"
- 1 张 card:summary "selected LanceDB for embedded vector store",引用
  `sess_platform-db` 的 round 1

通过 service 层直接 seed(`cli_env.app.state.sessions.ingest` /
`cli_env.app.state.cards.create`),不走 CLI 的 ingest/card —— 种子是 fixture
设置,不是被测行为。

## 覆盖的代码路径

- Click arg parsing(`query` 必填,`--top-k` 可选,无 `--where`)
- `cli/search.py` 构 body + `api()` POST
- `api/search.py` → `SearchService.search(SearchRequest(...))`
- `SearchService._search_cards`(query 非空 → hybrid 分支)
- `SearchService._search_sessions`(query 非空 → FTS 分支)
- LanceDB `hybrid_search_cards` + `fts_search_sessions`
- `extract_snippets` + jieba 分词(只验证被调用,不验证输出)
- 向 `search_log` SQLite 表 + `logs/search/YYYY-MM-DD.jsonl` 双写
- FastAPI 用 `response_model=SearchResponse` 序列化输出
