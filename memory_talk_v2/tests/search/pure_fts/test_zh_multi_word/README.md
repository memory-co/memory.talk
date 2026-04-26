# pure_fts / zh_multi_word

中文多词精确匹配 —— sessions 桶 FTS。query 用空格分隔的多个中文词,模拟
用户用关键词表达式搜索的场景。

## 探针(`probes.json`)

| 查询 | 预期 top-1 |
|---|---|
| `中文 全文 检索 选型`   | `sess_zh_fts_decision` |
| `异步 数据库 连接池`    | `sess_async_db_pool_zh` |
| `向量 索引 重建`        | `sess_vector_rebuild_zh` |
| `代码 评审 流程`        | `sess_code_review_zh` |
| `性能 监控 告警`        | `sess_perf_monitoring_zh` |

## 这个 case 在测什么

`_segment()` 对带空格的中文 query 行为 —— 期望 jieba 见到空格保持原样切分,
不会把"代码 评审"再合并。多个中文 token 同时落 FTS 倒排,文档命中越多排得
越靠前。这是 v1 时代就稳定的链路,跌出 Excellent 通常意味着 jieba 字典或
tokenizer 配置改了。
