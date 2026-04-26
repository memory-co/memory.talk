# pure_fts / zh_single_word

中文(短)词组精确匹配 —— sessions 桶 FTS。query 是单个中文复合词
(2-4 个汉字),验证 jieba 切词后能命中只含该词的 session。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `向量数据库` | `sess_vector_db_zh` |
| `搜索引擎`   | `sess_search_engine_zh` |
| `异步编程`   | `sess_async_zh` |
| `嵌入式`     | `sess_embedded_zh` |
| `全文检索`   | `sess_fts_zh` |

## 这个 case 在测什么

中文 query 经 `_segment()` 走 jieba 切词后,FTS 倒排能否在 sessions 桶找到。
注意 jieba 默认词典对"向量数据库"会切成 `向量/数据库` 两个 token,probe
结果稳不稳取决于 corpus 里其他 session 是否也包含这两个词。
