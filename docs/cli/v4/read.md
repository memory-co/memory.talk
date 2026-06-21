# read

按 id 读一个对象,前缀自动判型:

```bash
memory.talk read <id> [--json]
```

| 前缀 / 分片 | 读到的 |
|---|---|
| `card_` | 一张卡:**问题 + 它所有答案**(+ IBIS 边 + 出处) |
| `card_…#p<n>` 分片 | **单个答案**(Position):`claim` + 顶踩计数 + 现算 credence + scope + 它收到的全部 review |
| `card_…#l<n>` 分片 | **单条边**(CardLink):`claim` + `type` + `target_id` + 顶踩计数 + 现算 credence + 它收到的全部 review |
| `sess_` | session(沿用 v3 形态)+ 末尾 `## marks (N)`——这条 session 上做过的 mark(每条:`m<n>` · indexes · 它的 `#…？` 建/连了哪些卡);0 条则不出这段 |
| `sess_…#m<n>` 分片 | **单条 mark**:场景(`description`)+ mark 全文 + `indexes` + `## issues`(每条 `#…？` → new card / linked 哪张卡) |

> Position / CardLink **都没有独立 id**——都是所属卡的附属,寻址 `card_…#p<n>` / `card_…#l<n>`。`parse_id` 认出 `card_` id 上的分片就分派:`#p<n>` → 那张卡的第 n 个 Position、`#l<n>` → 第 n 条 CardLink(跟它认 `sess_…#m<n>` 分派到 mark 一个路子)。

## `card_` —— 问题 + 它所有答案

读一张卡 = 问题 + 它**所有** Position(各自顶踩计数、现算 credence、scope)+ IBIS 边 + 出处。credence 最高的那个高亮 = 当下答案。

### 输出 — Markdown(默认)

`````markdown
# card `card_01jz8k2m`

**issue:** 用户偏好什么回答风格?

`created 2026-06-18 14:30` · 3 positions · 2 sessions

---

### ★ [POSITION] `card_01jz8k2m#p1` · `credence +6 · ↑7 ↓1 ·0`

默认简洁、要点优先

`scope: 日常问答;调试场景另说` · 2026-06-18 14:30

### [POSITION] `card_01jz8k2m#p2` · `credence +1 · ↑2 ↓1 ·3`

调试场景下要详细、带完整命令

`scope: (none)` · 2026-06-19 09:12

---

**links:** specializes → `card_01jzsub` · related `card_01jzrel`
**sessions:** `sess_abc` #11-15 · `sess_def` #3,7,12
`````

#### 约定

- 顶部 `# card <card_id>` + `**issue:**` 整段问题;第三行 metadata(创建时间 · Position 数 · 出处 session 数)。
- 每个 Position 一个 H3 块:`### [POSITION] \`card_…#p<n>\` · \`credence <现算分> · ↑<up> ↓<down> ·<neutral>\``。credence 现算(不是存的);**最高的那个标题前加 `★`** = 当下答案(平手按最近更新),**不是 `accepted` 字段**。
- 标题下整段 `claim`,再一行 `scope`(空则 `(none)`)+ 时间。
- 末尾 `**links:**`(IBIS 边)/ `**sessions:**`(出处),无则整段不出。

### 输出 — JSON(`--json`)

跟 [`POST /v4/read`](../../api/v4/read.md) 的 `card_` 响应同形(`issue` + `positions[]` 按 credence 降序 + `links` + `sessions`)。`credence` 是响应里现算的字段,不在存储里。字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

## `card_…#p` —— 单个答案 + 它的 review

### 输出 — Markdown(默认)

`````markdown
# position `card_01jz8k2m#p1` · `credence +6 · ↑7 ↓1 ·0`

> under card `card_01jz8k2m` — 用户偏好什么回答风格?

默认简洁、要点优先

`scope: 日常问答;调试场景另说` · created 2026-06-18 14:30

## reviews (10)

- `+1` `sess_def` #20-25 · 2026-05-30 10:00 — 又一次验证,简洁版接住了
- `-1` `sess_ghi` #3-8 · 2026-05-12 09:00 — 用户那次明显要详细
`````

#### 约定

- 标题 `# position card_…#p<n> · \`credence <现算分> · ↑<up> ↓<down> ·<neutral>\``,credence 现算(不是存的)。
- 第二行引用它所属卡的 `card_id` + `issue`(一句话定位)。
- 整段 `claim`,再一行 `scope`(空则 `(none)`)+ 创建时间。
- `## reviews (N)`:每条 `<argument> <session_id> #<indexes> · 时间 — comment`,按 `created_at` 倒序;无 review 时整段不出。

### 输出 — JSON(`--json`)

```json
{
  "card_id": "card_01jz8k2m",
  "position": "p1",
  "claim": "默认简洁、要点优先",
  "up_count": 7, "down_count": 1, "neutral_count": 0, "review_count": 8,
  "credence": 6,
  "scope": "日常问答;调试场景另说",
  "forked_from": null,
  "created_at": "2026-06-18T14:30:00Z",
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def", "indexes": "20-25", "argument": 1, "comment": "又一次验证", "created_at": "2026-05-30T10:00:00Z"}
  ]
}
```

`credence` 是响应里现算的字段,不在存储里。字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md) / [`review.md`](../../structure/v4/review.md)。

## `card_…#l` —— 单条边 + 它的 review

跟 `card_…#p` 同构,只是读的是一条 CardLink(受治理边):`claim`(这条边为什么成立)+ `type` + `target_id` + 顶踩计数 + 现算 credence + 它收到的全部 review。

### 输出 — Markdown(默认)

`````markdown
# link `card_01jz8k2m#l1` · `credence +4 · ↑4 ↓0 ·1`

> under card `card_01jz8k2m` — 用户偏好什么回答风格?
> **specializes** → `card_01jzyyyy`

本卡是它的一个特例 —— 都走同一套 auth,只是把范围收窄到 OAuth 回调这一段。

`created 2026-06-18 15:00`

## reviews (5)

- `+1` `sess_def` #30-34 · 2026-06-18 15:00 — 这条 specializes 边确实成立
`````

#### 约定

- 标题 `# link card_…#l<n> · \`credence <现算分> · ↑<up> ↓<down> ·<neutral>\``,credence 现算(不是存的);**低于阈值的边在 `read <card_id>` 的 links 段淡出**,但单独 `read card_…#l<n>` 总能读到。
- 第二行引用所属卡 `card_id` + `issue`;第三行 `**<type>** → <target_id>`。
- 整段 `claim`(这条边为什么成立)+ 创建时间。
- `## reviews (N)`:每条 `<argument> <session_id> #<indexes> · 时间 — comment`,按 `created_at` 倒序;无 review 时整段不出。

### 输出 — JSON(`--json`)

```json
{
  "card_id": "card_01jz8k2m",
  "link": "l1",
  "type": "specializes",
  "target_id": "card_01jzyyyy",
  "target_type": "card",
  "claim": "本卡是它的一个特例 —— 都走同一套 auth,只是把范围收窄到 OAuth 回调这一段。",
  "up_count": 4, "down_count": 0, "neutral_count": 1, "review_count": 5,
  "credence": 4,
  "created_at": "2026-06-18T15:00:00Z",
  "reviews": [
    {"review_id": "review_01jzr5kq", "session_id": "sess_def", "indexes": "30-34", "argument": 1, "comment": "这条边确实成立", "created_at": "2026-06-18T15:00:00Z"}
  ]
}
```

`credence` 是响应里现算的字段,不在存储里。字段语义见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md) / [`review.md`](../../structure/v4/review.md)。

## `sess_` —— session

读一条 session = 头部元数据(`meta`)+ 展开的 `rounds`,完全只读(不更新任何 stats;session 不参与卡的动力学)。rounds 一次性全返回,不支持窗口参数;session 过长时在 [`search`](search.md) 侧用更精准的 `query` / `--where` 缩小命中。

### 输出 — Markdown(默认)

````markdown
# SESSION `sess_187c6576`

**Created:** `2026-04-10`

**Metadata:**

- project: `/home/user/myapp`

**Source:** claude-code

## rounds (2)

**[#1 human]**

ChromaDB vs LanceDB?

---

**[#2 assistant]**

推荐 LanceDB,零依赖嵌入式。
````

约定:
- 顺序固定:**头部元数据**(`Created` / `Metadata` / `Source`)→ **`## rounds`**。每段元数据之间空行隔开;`Source` 跟其它元数据并排放头部(放最末尾会被长 rounds 推得看不见)。
- `## rounds` 放最后,因为单条 round 内容里**经常本身就是 Markdown**(代码块、列表、引用、子标题),放在中间会跟外层结构混。挪到最后等于"先看元数据,再看内容正文"。
- 每个 round 之间用 `---` 分隔。round 内部:第一行 `**[#<idx> <role>]**`,空一行后是 round 正文(原样输出 content 文本,可含任意 Markdown)。
- 多 ContentBlock 的 round(含 thinking 等非 text 块)用 `+ <type>` 标注:`**[#3 assistant +thinking +tool_use]**`。正文里只渲染 text/code 块,其它类型用头部 `+xxx` 标记。
- 单条 round 正文不做 80 列截断;完整 raw 内容仍在 `--json`。

### 输出 — JSON(`--json`)

```json
{
  "type": "session",
  "read_at": "2026-04-20T14:32:05Z",
  "session": {
    "session_id": "sess_187c6576",
    "source": "claude-code",
    "created_at": "2026-04-10T14:30:00Z",
    "metadata": {"project": "/home/user/myapp"},
    "rounds": [
      {
        "index": 1,
        "round_id": "r001",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}]
      },
      {
        "index": 2,
        "round_id": "r002",
        "speaker": "assistant",
        "role": "assistant",
        "content": [{"type": "text", "text": "推荐 LanceDB,零依赖嵌入式"}]
      }
    ]
  }
}
```

响应直接暴露**带前缀的裸 id**(`session_id`),拿到就能喂给下一次 `read`。session 结构见 [`../../structure/v4/session.md`](../../structure/v4/session.md)。

## 错误

| 情况 | 行为 |
|---|---|
| `id` 前缀不识别 | `error: invalid id prefix`,exit 1 |
| 对象不存在 | `error: <kind> '<id>' not found`,exit 1 |
