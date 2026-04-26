# fts_plus_vector / zh_multi_word

中文多词精确匹配 —— cards 桶 hybrid。空格分隔多个中文词作 query,FTS 命中
+ vector 召回 + RRF 融合。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `中文 全文 检索 选型`   | `card_zh_fts_decision` |
| `异步 数据库 连接池`    | `card_async_db_pool_zh` |
| `向量 索引 重建`        | `card_vector_rebuild_zh` |
| `代码 评审 流程`        | `card_code_review_zh` |
| `性能 监控 告警`        | `card_perf_monitoring_zh` |

## 这个 case 在测什么

中文多词 hybrid 链路:看 RRF 是否把"含全部 token 的卡"稳定排到第一。corpus 里
"向量数据库综述" 和 "向量索引重建流程" 都含"向量",有干扰可能 —— 但只有后者
含"重建"和"索引"两个词同时出现,FTS 应该把它顶到第一。
