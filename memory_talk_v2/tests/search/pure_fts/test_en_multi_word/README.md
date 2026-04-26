# pure_fts / en_multi_word

英文多词精确匹配 —— sessions 桶 FTS,query 是 2-4 个英文词,验证多词都能命中
同一个 session 的内容。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `vector database comparison` | `sess_vector_compare` |
| `async python middleware`    | `sess_async_middleware` |
| `memory talk skill overview` | `sess_memory_talk_intro` |
| `FTS inverted index`         | `sess_fts_design` |
| `rebuild from file truth`    | `sess_rebuild_design` |

## 这个 case 在测什么

LanceDB FTS 多词查询的默认行为(默认是 OR 匹配,文档命中越多 token 排名越高)。
跌出 Excellent 多半意味着多词聚合排序的逻辑变了。
