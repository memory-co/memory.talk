# review

对一张 card 的"回帖"——card 像一个帖子,review 是后续会话里对它的态度表态。可以**支持(+1)、中立(0)、反对(-1)**,附带某次 session 里的证据 rounds 和一段说明 comment。

```bash
memory.talk review '<json>' [--json]
```

输入 JSON 结构:

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_abc123",
  "indexes": "20-25",
  "score": 1,
  "comment": "三个月后再次确认 LanceDB 选型有效——SQLite + LanceDB 混合栈生产跑稳"
}
```

## 字段

- `card_id`(必填):被 review 的 card,必须是 `card_<...>`;不存在或前缀错返 400。
- `session_id`(必填):本次 review 所在的 session,必须是 `sess_<...>`。**一个 review 只挂一个 session** —— 跟 card 不同(card 的 `rounds` 可跨多 session),review 是"某次具体对话里的一次表态",语义上单 session。
- `indexes`(必填):证据 round 范围,语法跟 [card.md#indexes 语法](card.md#indexes-语法) 完全一致(`"20-25"` 区间或 `"3,7,12"` 离散列表;严格单调递增;越界报错)。
- `score`(必填):`1` 支持 / `0` 中立(纯备注) / `-1` 反对。其它整数或非数值报错。
- `comment`(可选):一段说明这次 review 的人话。`score=0` 时强烈建议填上 —— 否则这条 review 等于"看到了但没说什么",信号弱。服务端不强制。
- `review_id`(可选):不提供则自动生成 `review_<ULID>`,传入时必须是 `review_<...>` 形态。

> 同一对 `(card_id, session_id)` **可以有多条 review** —— 一次对话里可能在不同位置对同一张 card 表态多次(早期反对、深入后转支持)。每条由不同的 `indexes` 区分。服务端**不去重**。

## 输出

### Markdown(默认)

````markdown
ok: created `review_01jzr5kq` · `card_01jz8k2m` **+1** by `sess_abc123` #20-25
````

错误(到 stderr,exit 1):

````markdown
**error:** score must be one of 1, 0, -1 (got 2)
````

````markdown
**error:** index 99 out of range for session `sess_abc123`
````

````markdown
**error:** card `card_01jzNotExist` not found
````

### JSON(`--json`)

```json
{
  "status": "ok",
  "review_id": "review_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_abc123",
  "score": 1
}
```

```json
{"error": "score must be one of 1, 0, -1 (got 2)"}
```

## 副作用

- 校验:`card_id` 存在;`session_id` 存在且 `indexes` 不越界;`score ∈ {-1, 0, 1}`。任一失败,整条不落库。
- **累加被 review 的 card 的 stats**(详见 [read.md](read.md) 的 `card.stats`):
  - `review_count += 1`(无论 `score` 是什么)
  - `score = 1` → `review_up += 1`
  - `score = -1` → `review_down += 1`
  - `score = 0` → `review_neutral += 1`(中立 review 单独计数,不进 `review_up` / `review_down`,在沉浮公式里默认权重为 0,但保留了"被讨论广度"这条独立信号)
- 在 log 里追加 `reviewed` 事件,detail 含 `review_id` / `score` / `session_id` / `indexes`。
- review 自身**不进向量索引** —— `comment` 是辅助说明,不参与检索(检索 card 时按 card 的 `insight` 匹配,review 跟着 card 一起呈现)。

## 读取

review **不单独 read** —— 它依附于 card,在 `read card_xxx` 的输出里以 `## reviews` 区块列出。详见 [read.md](read.md)。

需要 raw 列表(脚本 / 调试)走 `read card_xxx --json`,响应体里 `card.reviews` 是按 `created_at` **倒序**的数组。

## 跟 card 的边界

| | `card` | `review` |
|---|---|---|
| 角色 | 沉淀一条认知 | 对认知的后续表态 |
| 时序 | 先 | 后(必须 card 已存在) |
| session 引用 | `rounds` 可跨多 session | 单 session |
| 内容载荷 | `insight` + 展开的 round 文本 | `score` + `comment` |
| 是否进向量 | 是(`insight` 做 embedding) | 否 |
| 增删改 | append-only(创建后不可改) | 同上 |

## 推荐姿势

```bash
# 三个月后再翻到这张 card,觉得当时的选型仍然成立
memory.talk review '{
  "card_id": "card_01jz8k2m",
  "session_id": "'"$SESSION_ID"'",
  "indexes": "20-25",
  "score": 1,
  "comment": "再次确认 LanceDB 选型,生产跑了 3 个月稳定"
}'

# 翻到一张 card,发现当时的判断错了
memory.talk review '{
  "card_id": "card_01jz0xnq",
  "session_id": "'"$SESSION_ID"'",
  "indexes": "3-8",
  "score": -1,
  "comment": "原以为 mmap NFS 没事,生产撞了 inode lock 的坑"
}'

# 仅备注,无明确正负
memory.talk review '{
  "card_id": "card_01jz8k2m",
  "session_id": "'"$SESSION_ID"'",
  "indexes": "11",
  "score": 0,
  "comment": "又一次提到这张卡,场景是迁移评估,没改变结论"
}'
```
