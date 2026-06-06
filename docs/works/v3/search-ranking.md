# Search ranking

`memory.talk search` 的混合 FTS + 向量召回 + 公式排序流水线,加上 `--recall` 调试视角跟主搜索的区别。

相关:
- CLI: [`../../cli/v3/search.md`](../../cli/v3/search.md)
- API: [`../../api/v3/search.md`](../../api/v3/search.md)
- DSL 语法: [dsl.md](dsl.md)
- 论坛动力学(stats 的来源): [forum-dynamics.md](forum-dynamics.md)

## 召回与排序两步

```
query  ──▶  LanceStore.search_cards()  / search_rounds()
              │  hybrid: FTS over text + cosine over vector
              │  RRF 合并 → relevance 分
              ▼
           候选 cards + 候选 sessions(按 hits 聚合)
              │
              ▼
           SearchService._score(candidate)
              │  按 settings.search.ranking_formula 跑
              ▼
           final score → 降序 → 截 top_k
```

## 公式可用变量

| 变量 | 来源 | 备注 |
|---|---|---|
| `relevance` | RRF 相关度 | 空 query 时全置 0 |
| `review_up` / `review_down` / `review_neutral` / `review_count` | `card_stats` 表 | sessions 候选全置 0 |
| `read_count` | `card_stats.read_count` | sessions 全置 0 |
| `recall_count` | 现算自 `recall_event`(见 [recall-pipeline.md](recall-pipeline.md)) | sessions 全置 0 |
| `age_days` | `now - created_at` 天数 | 两类候选都有 |

跨 card / session 的可比性来自:**两类候选都过同一公式**。card 有 stats 字段,session 这些项统一置 0,`relevance` 这一项在两边同尺度上比较。

## 0.8.x 默认公式:裸 `relevance`

```
ranking_formula = "relevance"
```

不掺 stats。理由:`search` 是主动调用,query 通常是关键词或 identifier(`vvp-ai` / `LanceDB` / `AONE_SANDBOX_ID`),用户意图是**找最相关的内容**。

早期版本默认带 `+ 0.02 * log(read_count + 1)` 这类沉浮项时,一张"被看过 5 次但弱相关"的 card 可以反超"精确命中但 read=0"的 card,实践中误排明显(见 `docs/report/2026-05-30-search-vvp-ai-hyphen-identifier.md`)。0.8.x 把默认收敛为 `relevance` 一项,让"主动搜索的人想要精确"这件事按本能生效。

公式仍走 settings,**不进 CLI 参数** —— 想要论坛动力学回来就改成例如:

```
relevance + 0.1 * (review_up - review_down) - 0.005 * age_days
```

## Shadow knowledge / 高争议查询

排序由当前 `ranking_formula` 决定 —— 默认 `relevance` 下空 query 大家相关度都是 0,顺序意义不大。

真要按 stats 排序去 surface shadow:
1. 临时切到带 stats 的 `ranking_formula`,看完再切回 `relevance`,或者
2. 用 [`--recall` 调试视角](#--recall-调试视角)看 cards-only RRF 排序

DSL 仍然可以过滤,只是顺序不一定有意义:

```bash
memory.talk search "" -w 'read_count > 10 AND review_count = 0'
memory.talk search "" -w 'review_up >= 3 AND review_down >= 3'
memory.talk search "" -w 'review_down > review_up'
```

## `--recall` 调试视角

主动搜索默认按 `ranking_formula` 排,而 `recall`(hook 阶段自动召回)走另一条路径,**完全不跑公式**,直接按 LanceDB cards 表的 hybrid RRF 顺序返回。

想在不实际触发 recall 的情况下"预览"那条路径会返回什么、按什么顺序:

```bash
memory.talk search "vvp-ai" --recall

# 加 --session 模拟某个 session 的 recall_event dedup
memory.talk search "vvp-ai" --recall --session sess-15f0a7fb-...
```

`--recall` 跟主动搜索的 4 点区别:

1. **cards-only** —— 跟 recall 接口一致,不返回 session results
2. **跳过 `ranking_formula`** —— 用裸 RRF relevance 排序,不掺 stats
3. **`--session` 触发 dedup 预览** —— 把该 session `recall_event` 已记的 card 从结果里过滤掉
4. **完全只读** —— **不写 `recall_event`**,**不**让 derived `recall_count` 增长,审计在 `search_log` 用 `mode=recall` 标识

跟 `--where` 兼容,跟 `--top-k` / `--json` 兼容。`--session` 单独用(不带 `--recall`)会报错。

## Session 候选怎么算 final score

session 桶聚合方式(可配,默认 `1 - prod(1 - score_i)` 衰减聚合):

```
session.relevance = aggregate(hits[*].score)
session.final_score = ranking_formula(env)   # 同上,stats 全 0
```

session 内部按 `hit_count` / `hits_shown` 表示,默认上限 3 条 hits 展示。多于这些命中的 round 仍计入 `hit_count`,但不出现在 response 里。

## 审计

每次 search 都会在服务端 `search_log` 表 + `logs/search/<UTC 日期>.jsonl` 里追加一条 —— **存的是完整响应体**(含 `results[]` 全部字段,session hits 含完整上下文窗)。事后审计能复原"当时用户看到了什么",即便 sync 给 session 追加了新 round、card 拿到新 review 也能追回原样。

这是**纯审计** —— 不做"凭据发行",不参与任何后续调用的校验。

search_log 默认永久保留。老化策略见 `settings.search.search_log_retention_days`。
