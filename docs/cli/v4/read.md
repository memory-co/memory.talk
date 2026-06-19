# read

按 id 读一个对象,前缀自动判型:

```bash
memory.talk read <id> [--json]
```

| 前缀 | 读到的 |
|---|---|
| `card_` | 一张卡:**问题 + 它所有答案**(+ IBIS 边 + 出处) |
| `pos_` | **单个答案**(Position):`claim` + 顶踩计数 + 现算 credence + scope + 它收到的全部 review |
| `sess_` | session(沿用 v3 形态) |

调 [`POST /v4/read`](../../api/v4/read.md)。

## `card_` —— 问题 + 它所有答案

读一张卡 = 问题 + 它**所有** Position(各自顶踩计数、现算 credence、scope)+ IBIS 边 + 出处。credence 最高的那个高亮 = 当下答案。

### 输出 — Markdown(默认)

`````markdown
# card `card_01jz8k2m`

**issue:** 用户偏好什么回答风格?

`created 2026-06-18 14:30` · 3 positions · 2 sessions

---

### ★ [POSITION] `pos_01jzp3nq` · `credence +6 · ↑7 ↓1 ·0`

默认简洁、要点优先

`scope: 日常问答;调试场景另说` · 2026-06-18 14:30

### [POSITION] `pos_01jzr5kq` · `credence +1 · ↑2 ↓1 ·3`

调试场景下要详细、带完整命令

`scope: (none)` · 2026-06-19 09:12

---

**links:** specializes → `card_01jzsub` · related `card_01jzrel`
**sessions:** `sess_abc` #11-15 · `sess_def` #3,7,12
`````

#### 约定

- 顶部 `# card <card_id>` + `**issue:**` 整段问题;第三行 metadata(创建时间 · Position 数 · 出处 session 数)。
- 每个 Position 一个 H3 块:`### [POSITION] \`<pid>\` · \`credence <现算分> · ↑<up> ↓<down> ·<neutral>\``。credence 现算(不是存的);**最高的那个标题前加 `★`** = 当下答案(平手按最近更新),**不是 `accepted` 字段**。
- 标题下整段 `claim`,再一行 `scope`(空则 `(none)`)+ 时间。
- 末尾 `**links:**`(IBIS 边)/ `**sessions:**`(出处),无则整段不出。

### 输出 — JSON(`--json`)

跟 [`POST /v4/read`](../../api/v4/read.md) 的 `card_` 响应同形(`issue` + `positions[]` 按 credence 降序 + `links` + `sessions`)。`credence` 是响应里现算的字段,不在存储里。字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

## `pos_` —— 单个答案 + 它的 review

### 输出 — Markdown(默认)

`````markdown
# position `pos_01jzp3nq` · `credence +6 · ↑7 ↓1 ·0`

> under card `card_01jz8k2m` — 用户偏好什么回答风格?

默认简洁、要点优先

`scope: 日常问答;调试场景另说` · created 2026-06-18 14:30

## reviews (10)

- `+1` `sess_def` #20-25 · 2026-05-30 10:00 — 又一次验证,简洁版接住了
- `-1` `sess_ghi` #3-8 · 2026-05-12 09:00 — 用户那次明显要详细
`````

#### 约定

- 标题 `# position <pid> · \`credence <现算分> · ↑<up> ↓<down> ·<neutral>\``,credence 现算(不是存的)。
- 第二行引用它所属卡的 `card_id` + `issue`(一句话定位)。
- 整段 `claim`,再一行 `scope`(空则 `(none)`)+ 创建时间。
- `## reviews (N)`:每条 `<argument> <session_id> #<indexes> · 时间 — comment`,按 `created_at` 倒序;无 review 时整段不出。

### 输出 — JSON(`--json`)

```json
{
  "position_id": "pos_01jzp3nq",
  "card_id": "card_01jz8k2m",
  "claim": "默认简洁、要点优先",
  "up_count": 7, "down_count": 1, "neutral_count": 0,
  "credence": 6,
  "scope": "日常问答;调试场景另说",
  "forked_from_position_id": null,
  "created_at": "2026-06-18T14:30:00Z",
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def", "indexes": "20-25", "argument": 1, "comment": "又一次验证", "created_at": "2026-05-30T10:00:00Z"}
  ]
}
```

`credence` 是响应里现算的字段,不在存储里。字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md) / [`review.md`](../../structure/v4/review.md)。

## `sess_` —— session

沿用 v3 的 session 读取(`meta` + `rounds`),见 [`../v3/read.md`](../v3/read.md)。

## 错误

| 情况 | 行为 |
|---|---|
| `id` 前缀不识别 | `error: invalid id prefix`,exit 1 |
| 对象不存在 | `error: <kind> '<id>' not found`,exit 1 |
