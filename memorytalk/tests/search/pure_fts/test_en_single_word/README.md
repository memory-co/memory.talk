# pure_fts / en_single_word

英文单词精确匹配 —— 在 sessions 桶(FTS-only)上验证一个英文单词能定位到含
该词的 session。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `LanceDB`     | `sess_lancedb` |
| `FastAPI`     | `sess_fastapi_mw` |
| `Pinecone`    | `sess_pinecone` |
| `PostgreSQL`  | `sess_postgres` |
| `Kubernetes`  | `sess_k8s` |

## 评分

每条 probe 用 MRR(rank=1 → 1.0,rank=2 → 0.5,...,not in top-5 → 0),
5 条均值落到 5 档 quality gate(详见 `tests/search/README.md`)。

## 这个 case 在测什么

`whitespace` tokenizer 是否对英文单词正确建立 FTS 倒排,以及 sessions 桶的
`fts_search_sessions` 路径是否能把唯一含该词的 session 排到第一。这是 FTS
的最基本能力,跌出 Excellent 通常意味着 tokenizer / 索引重建出问题了。
