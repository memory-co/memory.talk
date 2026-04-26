# fts_plus_vector / en_single_word

英文单词精确匹配 —— cards 桶,FTS + 向量召回经 RRF 融合。预期 hybrid 至少
不应该比纯 FTS 差(exact match 是 FTS 的强项,vector 不应造成倒退)。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `LanceDB`     | `card_lancedb` |
| `FastAPI`     | `card_fastapi_mw` |
| `Pinecone`    | `card_pinecone` |
| `PostgreSQL`  | `card_postgres` |
| `Kubernetes`  | `card_k8s` |

## 这个 case 在测什么

`hybrid_search_cards` 路径:DashScope 嵌入 + LanceDB FTS,经 `RRFReranker(K=60)`
融合后的 top-1 命中率。如果 vector 信号在 RRF 中权重过大、把 FTS 的精确命中
冲掉,这一档会跌出 Excellent —— 是个 RRF 调参的早期警报。
