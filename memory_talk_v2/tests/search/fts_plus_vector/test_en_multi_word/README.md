# fts_plus_vector / en_multi_word

英文多词精确匹配 —— cards 桶 hybrid。多 token query 在 RRF 后是否仍能稳定
top-1 命中目标 card。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `vector database comparison` | `card_vector_compare` |
| `async python middleware`    | `card_async_middleware` |
| `memory talk skill overview` | `card_memory_talk_intro` |
| `FTS inverted index`         | `card_fts_design` |
| `rebuild from file truth`    | `card_rebuild_design` |

## 这个 case 在测什么

多词 query 在 hybrid 路径下的稳定性:FTS 给出 token 级匹配排名,vector 给出
语义相近排名,RRF 取 top-K 平均。当 corpus 里某些 card 的 summary 跟 query
语义相近但词面不同(改写),vector 召回会跟 FTS 抢位置 —— exact match 是个
良性场景,vector 不应抢错。
