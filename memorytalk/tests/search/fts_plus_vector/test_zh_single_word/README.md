# fts_plus_vector / zh_single_word

中文单词精确匹配 —— cards 桶 hybrid。短中文 query 在 jieba 切词 + DashScope
中文嵌入 + RRF 三段链路下的 top-1 命中。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `向量数据库` | `card_vector_db_zh` |
| `搜索引擎`   | `card_search_engine_zh` |
| `异步编程`   | `card_async_zh` |
| `嵌入式`     | `card_embedded_zh` |
| `全文检索`   | `card_fts_zh` |

## 这个 case 在测什么

中文 hybrid 链路是否对短词查询稳定。DashScope `text-embedding-v4` 对中文支持
不错,但在"向量数据库" vs "向量索引" 这种字面相近、语义不同的对子里,vector
可能把"向量索引重建"那张卡顶上来 —— 实际是否发生看 baseline 漂移。
