# card

v4 卡的写入 + 查看入口。一张卡 = **一个问题(Issue)+ 若干答案(Position)**,所以 `card` 拆成两条子命令:

```
memory.talk card
├── create (--card <cid> | --issue '<问题>') --answer '<答案>' [--cite <sid>:<indexes> ...] [--scope '<场景>'] [--json]
│                                                    # 建新问题 / 给老问题加一个答案
└── view <card_id> [--json]                          # 看一张卡:问题 + 它所有答案(各自 credence / 顶踩 / scope)
```

表态(顶/踩某个答案)走 [`review`](review.md);"按相关度找卡"走 [`../v3/search.md`](../v3/search.md);hook 召回走 [`recall`](recall.md)。

> `card` 是 group 命令,不带子命令调用直接打印 help。设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## card create

在一张卡下创建一个候选答案(Position);没给 `--card` 时先建一张新卡(新问题)。

```bash
memory.talk card create \
    (--card <card_id> | --issue '<问题文本>') \
    --answer '<答案文本>' \
    [--cite <session_id>:<indexes> ...] \
    [--scope '<适用场景描述>'] \
    [--json]
```

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--issue` | 二选一 | 新建一张卡,`issue` = 这句问题文本(也是 embedding 锚点)。与 `--card` 互斥 |
| `--card` | 二选一 | 给已有卡 `<card_id>`(`card_<…>`)加答案,不新建卡。与 `--issue` 互斥 |
| `--answer` | 是 | 这个候选答案的文本(`claim`,内联在 Position 上,不单独建节点、不共享) |
| `--cite` | 否,可多次 | 出处:`<session_id>:<indexes>`,每个落一条 `card_sessions`。支持多 session(多次 `--cite`) |
| `--scope` | 否 | 一句话**适用场景**描述(`scope`,软提示,非门禁;负边界如「别用于育儿」直接写进这句) |
| `--card_id` / `--position_id` | 否 | 显式指定 id;不提供则自动生成 `card_<ULID>` / `pos_<ULID>` |

详细字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### `--issue` vs `--card`(必须二选一)

- `--issue '<问题>'`:**建新卡**——新问题落 `cards`,再在其下落第一个 Position(`--answer`)。用于"冒出一个图里还没有的新问题"。
- `--card <cid>`:**复用老卡**——只在 `<cid>` 下加一个**竞争 Position**。用于"这个问题已经在图里,我有个(不同的)答案"。

两者**不能同时给**(报错),也**不能都不给**(报错)。"这是新问题还是老问题"的判定本身由上游写路径的检索 miss/hit 决定(见 [`../../works/v4/card.md`](../../works/v4/card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question));CLI 这层只执行已定的那一岔。

### `--cite` 语法 / indexes

每个 `--cite` 形如 `<session_id>:<indexes>`,`indexes` 语法沿用 v3:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `sess_abc:11-15` | 闭区间 `[11,15]`,展开 `11..15` |
| 列表 | `sess_abc:3,7,12` | 离散 index 列表 |

约束(不满足整次拒绝):**严格单调递增**(`15-11` / `12,7,3` 报错);**越界 / session 不存在** 报错。多个 `--cite` 各落一条 `card_sessions`(`position_id` 指向新建的这个答案)。

### 输出 — Markdown(默认)

新建卡 + 答案:

````markdown
ok: created `card_01jz8k2m` (issue) · `pos_01jzp3nq` (answer)
````

给老卡加答案:

````markdown
ok: `pos_01jzr5kq` (answer) under `card_01jz8k2m`
````

错误(到 stderr,exit 1):

````markdown
**error:** index 99 out of range for session `sess_abc`
````

### 输出 — JSON(`--json`)

```json
{"status": "ok", "card_id": "card_01jz8k2m", "position_id": "pos_01jzp3nq", "card_created": true}
```

`card_created` 标明这次是不是顺带新建了卡(`--issue` 走 true,`--card` 走 false)。返回的 `position_id` 就是以后 `review` 的对象。

### 副作用

- `--issue`:落 `cards`(`issue` + `created_at`)+ 计算 `issue` 的 embedding 写向量库(检索锚点)。
- 在卡下落一个 Position:`claim`(内联)+ `up/down/neutral_count` 初始化为 0 + `scope`(默认 `''`)。**不算 credence**(读时现算)。
- 每个 `--cite` 落一条 `card_sessions`(`card_id` + `session_id` + `position_id` + `indexes`);校验 indexes 不越界,失败整条不落库。
- 文件罐:`cards/<bucket>/<card_id>/card.json`(问题不可变)、`positions/<pid>.json`(答案 `claim` 不可变);计数 / `scope` / 边 / 出处是 SQLite 派生运行态。详见 [`../../structure/v4/filesystem.md`](../../structure/v4/filesystem.md)。

### 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `--issue` 和 `--card` 同时给 / 都不给 | `error: provide exactly one of --issue / --card`,exit 1 |
| `--answer` 缺失 / 空 | `error: --answer required`,exit 1 |
| `--card` 指向的卡不存在 | `error: card 'card_xxx' not found`,exit 1 |
| `--cite` 的 session 不存在 | `error: session 'sess_xxx' not found`,exit 1 |
| `--cite` 的 indexes 越界 / 非单调 | `error: index N out of range ...` / `indexes must be monotonically increasing`,exit 1 |
| 显式 id 前缀错 / 已存在 | `error: invalid <kind>_id prefix` / `... already exists`,exit 1 |

---

## card view

看一张卡:问题 + 它**所有** Position(各自的顶踩计数、现算 credence、scope、出处),credence 最高的那个高亮 = 当下答案。

```bash
memory.talk card view <card_id> [--json]
```

### 输出 — Markdown(默认)

`````markdown
# card `card_01jz8k2m`

**issue:** 用户偏好什么回答风格?

`created 2026-06-18 14:30` · 3 positions · 2 sessions

---

### ★ [POSITION] `pos_01jzp3nq` · `credence +6 · ↑7 ↓1 ·0`

默认简洁、要点优先

`scope: 日常问答;调试/教学场景另说` · 2026-06-18 14:30

### [POSITION] `pos_01jzr5kq` · `credence +1 · ↑2 ↓1 ·3`

调试场景下要详细、带完整命令

`scope: (none)` · 2026-06-19 09:12

### [POSITION] `pos_01jzx7aa` · `credence 0 · ↑0 ↓0 ·0`

其实用户要的是"可调档"

`scope: (none)` · 2026-06-19 10:01

---

**links:** specializes ← `card_01jzsub` · related `card_01jzrel`
**sessions:** `sess_abc` #11-15 · `sess_def` #3,7,12
`````

#### 约定

- 顶部 `# card <card_id>`,下面 `**issue:**` 整段问题文本;第三行 metadata(创建时间 · Position 数 · 出处 session 数)。
- 每个 Position 一个 H3 块:`### [POSITION] \`<pid>\` · \`credence <现算分> · ↑<up> ↓<down> ·<neutral>\``。
  - **credence 现算**(`up−down` 或 Wilson),不是存的;`↑↓` 是 `up_count` / `down_count`,`·N` 是 `neutral_count`。
  - **credence 最高**的那个块标题前加 `★`(= 当下答案;平手按最近更新)。**这不是 `accepted` 字段**,只是 view 时排出来的高亮。
  - 标题下整段 `claim`,再一行 `scope`(空则 `(none)`)+ 时间。
- 末尾 `**links:**`(IBIS 边,见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md))和 `**sessions:**`(出处,见 [`../../structure/v4/card-session.md`](../../structure/v4/card-session.md)),无则整段不出。

### 输出 — JSON(`--json`)

```json
{
  "card_id": "card_01jz8k2m",
  "issue": "用户偏好什么回答风格?",
  "created_at": "2026-06-18T14:30:00Z",
  "positions": [
    {
      "position_id": "pos_01jzp3nq",
      "claim": "默认简洁、要点优先",
      "up_count": 7, "down_count": 1, "neutral_count": 0,
      "credence": 6,
      "scope": "日常问答;调试/教学场景另说",
      "forked_from_position_id": null,
      "created_at": "2026-06-18T14:30:00Z"
    }
  ],
  "links": [{"type": "specializes", "target_id": "card_01jzsub", "dir": "in"}],
  "sessions": [{"session_id": "sess_abc", "position_id": "pos_01jzp3nq", "indexes": "11-15"}]
}
```

- `credence` 是**响应里现算**的字段(后端按 `up/down` 算后回填),**不在存储里**——别期望写得回去。
- `positions` 默认按 credence 降序(平手按最近更新)。
- 字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### 错误

| 情况 | 行为 |
|---|---|
| `card_id` 不存在 | `error: card 'card_xxx' not found`,exit 1 |
| 前缀错 | `error: invalid card_id prefix`,exit 1 |

---

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 冒出一个新问题 + 第一个答案 | `card create --issue '<Q>' --answer '<A>' --cite ...` |
| 给已有问题补一个竞争答案 | `card create --card <cid> --answer '<A>' --cite ...` |
| 看一张卡的所有答案 / 当下答案 | `card view <card_id>` |
| 对某个答案顶 / 踩 / 中立 | `review <position_id> <+1\|0\|-1> --cite ...` |
| 按相关度找卡 | `search <query>`(沿用 v3) |
| hook 阶段无意识召回 | `recall <session_id> <prompt>` |
| 连两张卡(IBIS 边) | `card-links`(API,见 [`../../api/v4/card-links.md`](../../api/v4/card-links.md)) |

> **改主意 ≠ 改卡**:答案错了不改 `claim`,而是 `card create --card <同一卡>` 加一个新答案 + `review <旧pid> -1` 踩旧的;credence 现算会把新答案抬上来,旧答案留作认知史。
