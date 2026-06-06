# Forum dynamics(论坛动力学)

v3 把记忆当**论坛**而非仓库。Card 不是被静态存进去等检索,而是被持续讨论、引用、赞踩、路过 —— 这些信号累计成 `card.stats`,公式驱动它的"沉浮"。

相关:
- 排序公式怎么消费 stats: [search-ranking.md](search-ranking.md)
- Card 的 stats schema: [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)

## 三轴信号

| 信号 | 来源 | 角色 | 字段 |
|---|---|---|---|
| **Review** | 用户/LLM 显式打分(`memory.talk review`) | quality(被赞还是被踩) | `review_up` / `review_down` / `review_neutral` / `review_count` |
| **Read** | `memory.talk read <card_id>` | engagement(被深入看) | `read_count` |
| **Recall** | hook 自动召回(`recall hook`)新返回(不是 dedup'd) | popularity(被路过过几次) | `recall_count` —— 0.9.0 起改为**派生**(详见下) |

三类信号互相独立累加,公式按权重合成 final score。

## 跟 Review / Recall 的关系图

```
[hook]  user prompts → RecallEvent 记录"展示了 K 张卡"(无判定)
                            ↓
                        LLM 在 response 里用了这些卡
                            ↓
[optional, 大多数情况不发生]
                        user/LLM 显式调 review,Review 记"对这张卡我赞 / 踩 / 中立"
```

| | Recall | Review |
|---|---|---|
| 时机 | hook 时,**LLM 还没回答** | 看完 LLM 答案之后 |
| 触发 | 自动 | 显式(几乎从不自动) |
| 是否一定发生 | 每个 user prompt 必有 | 大多数 recall **没有**后续 review |
| 单事件 ↔ 卡 | 1 事件 ↔ K 张卡(top-K) | 1 review ↔ 1 张卡 |
| 必有字段 | `prompt` / `returned_ids` / `skipped_ids` | `score` / `comment` / `indexes` |
| 论坛角色 | **popularity 信号** —— 卡的"分母" | **quality 信号** —— 卡的"分子" |

**两者都参与论坛动力学**,但角色不同。Ranking 公式同时用这两组信号。

## 为什么不合并 Recall 和 Review

考虑过"用 Review 同时承担'被展示'和'被评价'":每次 hook 给返回的卡都建一条 `score=null` 的 Review,后续真判定时 update score。

否决理由:

1. **Review 是 append-only + immutable**。改 score 破坏核心契约。
2. **Review 要 `indexes`**(哪几个 round 的证据)—— hook 时 LLM 还没回答,根本没有 round 可引用。
3. **Review 不存 prompt 也不存 skipped** —— 字段对不上。
4. **大量 `score=null` 的 review 把"review 是表态"的语义稀释了**。形似神不似。

所以保留两个对象,通过 `card.stats` 间接 join:`recall_count` 是 popularity,`review_count` / `review_up` / `review_down` 是 quality。

Review 未来可选反向引用 `recall_event_id`(supplemental audit field),0.9.x 范围外。

## 0.9.0:`recall_count` 改为派生

旧设计:`card_stats.recall_count` 是独立列,recall hook 触发时 `+= 1`。

问题:`recall_event` 写入和 `card_stats` UPDATE **不在一个事务里**,进程崩了会**永久 drift 且无人察觉**。

新设计:`recall_count` **完全派生**自 `recall_event.returned_ids`:

```sql
SELECT j.value AS card_id, COUNT(*) AS recall_count
FROM recall_event, json_each(recall_event.returned_ids) AS j
WHERE j.value IN (?, ?, ...)
GROUP BY j.value
```

search/read 展示时 bulk 一次查所有候选卡的 recall_count。SQLite 在百卡量级是 ms 级。

代价:每次 search/read 多一次 join。
换回:**结构上不可能 drift**,single source of truth。

详见 [recall-pipeline.md](recall-pipeline.md) § 派生的 `recall_count`。

## Ranking 公式怎么消费这些信号

公式可见的变量(详见 [search-ranking.md](search-ranking.md)):

- `relevance` — RRF 相关度
- `review_up` / `review_down` / `review_neutral` / `review_count`
- `read_count`
- `recall_count`
- `age_days`

0.8.x 默认公式是**裸 `relevance`** —— 不掺 stats。理由是主动搜索的用户想要精确,不想被 stats 反超(详细分析见 [search-ranking.md § 0.8.x 默认公式](search-ranking.md#08x-默认公式裸-relevance))。

想让论坛动力学回来:改 `settings.search.ranking_formula`,例如:

```
relevance + 0.1 * (review_up - review_down) - 0.005 * age_days
```

## 沉浮信号:fork 与 supersede

Card 的 lineage(`source_cards`)也是论坛动力学的一部分:

| 关系 | 含义 | 沉浮影响 |
|---|---|---|
| `derives_from` | 这张 card 是从另一张 card 衍生而来 | 间接(创建竞争对手,降低被引用源的相对地位) |
| `supersedes` | 这张 card 取代了另一张 card | 直接(强信号:旧 card 已过时) |

`source_cards` 是 create-time 决定的、create-time-immutable 的引用,做不到事后回填。

Card 删除时 inbound `source_cards` 不级联(详见 [card-deletion-flow.md](card-deletion-flow.md)),其他 card 的引用变成 dangling,但保留"曾经引用过"的事实。
