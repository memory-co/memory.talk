# Read 副作用

`POST /v3/read` / `memory.talk read <card_id>` 在读 card 时会 bump `read_count` + 写事件。Session read 是纯读,无副作用。

相关:
- CLI: [`../../cli/v3/read.md`](../../cli/v3/read.md)
- API: [`../../api/v3/read.md`](../../api/v3/read.md)

## Card read 的副作用

```
1. 查 card 存在 → 不存在返 404
2. SQLite tx:
   - UPDATE card_stats SET read_count = read_count + 1
3. append cards/<...>/events.jsonl 的 read_at 事件
4. 返回 card payload + stats(含刚 bump 完的 read_count)+ reviews + source_cards
```

`read_count` 跟其他 stats 一起喂给 [search-ranking.md](search-ranking.md) 的公式。在默认公式(裸 `relevance`)下,read_count 不影响排序;改了公式就生效。

## Session read 是纯读

```
1. 查 session 存在 → 不存在返 404
2. 读 sessions/<...>/rounds.jsonl 全文
3. 返回 session 元数据 + rounds + (不动任何 counter,不写任何 event)
```

为什么 session read 不算副作用:session 不参与论坛动力学(sessions 没有 `read_count` / `review_*` stats)。看 session 是看原始对话,不是看一条"认知主张"。

## `read_count` 的语义

read_count 累加规则:

- 同一 `card_id` 在同一秒里被 read 多次 → 累加多次(没有去重)
- 通过 API / CLI / 任何路径 read 都算
- search/recall 返回 card 不算 read(那只是"提到了它",没有"展开看它")
- `recall hook` 把 card_id 放进 LLM context 也不算 read(同上)

设计意图:read_count 是**人类(或 LLM)主动展开 card 详情**的计数,反映"engagement deep dive",跟 recall_count(被路过)、review_count(被评价)分开做三个独立信号。

## 没有 unread / view_count 区分

只有一个 `read_count`,不区分"第一次 read"还是"第 N 次 re-read"。

理由:论坛动力学层面"被人反复看"是个连续信号,不是离散事件。一张 card 被同一人反复看 10 次 vs 被 10 个人各看一次,从"它有多重要"的角度看,两者**没有本质区别**(用户 identity 我们也没追踪)。

## 不进 vector index

read 这个操作本身不进任何 vector 索引,也不修改 card.json。**card payload 是 immutable 的**;read_count 在 SQLite 的 `card_stats` 表里,跟 payload 完全解耦。
