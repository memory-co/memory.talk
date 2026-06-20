# Search Result

**v4 搜索结果形态跟 v3 不同 —— 不要照搬 v3 那套沉浮 / forum 排序。** 本页只澄清差异并指向权威形态。

## v4 不是 v3 那套

| | v3 search-result | v4 search-result |
|---|---|---|
| 排序 | 单一融合 `ranking_formula`(吃 review_up/down + read_count + age),card / session 混排 | **撞问题** 检索;每卡现算 `credence`,**无 v3 沉浮 / forum 排序** |
| 每条结果 | 一句 insight + stats 6 计数 | 一张卡(Issue)+ `top_position`(当下答案)+ 现算 `credence` |
| read / recall 进排序 | 是(`read_count` / `recall_count` 进公式) | **否** —— 相关性只在召回那一刻检索现算,不回写、不进排序 |
| 「当下答案」 | 沉浮排序算 | `top_position` = credence 最高的 Position(平手按最近更新),无 `accepted` |

v4 把 v3 的沉浮三轴 / engagement 计数 / 融合排序公式**整套删掉**;命中卡带的是它的**当下答案**(`top_position`)+ 该答案的**现算 credence**,而不是一句陈述加 stats。

## 权威形态

v4 搜索结果的**权威字段定义**不在本页(本页只澄清「不是 v3 那套」),见:

- HTTP 响应形态 / `where` DSL 字段:[`../../api/v4/search.md`](../../api/v4/search.md)
- 卡 + Position + 现算 credence + 「当下答案」语义:[`card.md`](card.md)(见其 Schema 小节与「现算(不落库)」小节)

> v3 的 search-result 结构(融合排序 + SearchLog)见 [`../v3/search-result.md`](../v3/search-result.md),仅供对照,**v4 不沿用**。
