# card

v4 卡的写入 + 查看入口。一张卡 = **一个问题(Issue)+ 若干答案(Position)**,而 Card 和 Position 是**两个对象**——所以 `card` 拆成三条子命令:**建问题**、**加答案**、**看卡**:

```
memory.talk card
├── create --issue '<问题>' [--card_id <id>] [--json]
│                                                    # 建一张卡(只有问题;没答案也合法)
├── position --card <cid> --answer '<答案>' [--source <sid>:<indexes> ...] [--scope '<场景>'] [--position_id <id>] [--json]
│                                                    # 给一张卡加一个答案(Position)
└── view <card_id> [--json]                          # 看一张卡:问题 + 它所有答案(各自 credence / 顶踩 / scope)
```

表态(顶/踩某个答案)走 [`review`](review.md);"按相关度找卡"走 [`../v3/search.md`](../v3/search.md);hook 召回走 [`recall`](recall.md)。

> `card` 是 group 命令,不带子命令调用直接打印 help。设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## card create

建一张卡——**只立一个问题(`issue`),不带答案**。一张没有任何 Position 的卡是合法的(就是个还在等答案的问题,见 [`../../works/v4/card.md`](../../works/v4/card.md));答案另走 [`card position`](#card-position)。

```bash
memory.talk card create --issue '<问题文本>' [--card_id <id>] [--json]
```

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--issue` | 是 | 问题文本(`issue`),也是 embedding 锚点(检索撞的就是它)。值支持 `@<file>` / `@-`(见 [#文本字段:传文件--stdin](#文本字段传文件--stdin)) |
| `--card_id` | 否 | 显式指定 id;不提供则自动生成 `card_<ULID>` |

### 输出 — Markdown(默认)

````markdown
ok: created `card_01jz8k2m`
````

### 输出 — JSON(`--json`)

```json
{"status": "ok", "card_id": "card_01jz8k2m"}
```

### 副作用

- 落 `cards`(`issue` + `created_at`)+ 计算 `issue` 的 embedding 写向量库(检索锚点)。
- 文件罐:`cards/<bucket>/<card_id>/card.json`(问题不可变)。
- **不落任何 Position**——答案另走 `card position`。

### 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `--issue` 缺失 / 空 | `error: --issue required`,exit 1 |
| `--card_id` 前缀错 / 已存在 | `error: invalid card_id prefix` / `... already exists`,exit 1 |

---

## card position

给一张**已存在的卡**加一个答案候选(Position)。同一个问题下可以有多个答案,各自被顶踩、按现算 credence 竞争。

```bash
memory.talk card position \
    --card <card_id> \
    --answer '<答案文本>' \
    [--source <session_id>:<indexes> ...] \
    [--scope '<适用场景描述>'] \
    [--position_id <id>] \
    [--json]
```

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--card` | 是 | 给哪张卡(`card_<…>`)加答案;卡必须**已存在** |
| `--answer` | 是 | 答案文本(`claim`,内联在 Position 上,不单独建节点、不共享) |
| `--source` | 否,可多次 | 出处:`<session_id>:<indexes>`,每个落一条 `card_sessions`。支持多 session(多次 `--source`) |
| `--scope` | 否 | **这个答案(Position)的**一句话适用场景描述(`scope` 是 **Position 字段**,软提示、非门禁;负边界如「别用于育儿」直接写进这句)。不是卡级属性 |
| `--position_id` | 否 | 显式指定 id;不提供则自动生成 `pos_<ULID>` |

> **文本字段(`--answer` / `--scope`)的值都支持 `@<file>` / `@-`**:从文件 / stdin **原样**读入,专治内容里的引号、换行、`$`、反引号等特殊字符(见 [#文本字段:传文件--stdin](#文本字段传文件--stdin))。

详细字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### `--source` 语法 / indexes

每个 `--source` 形如 `<session_id>:<indexes>`,`indexes` 语法沿用 v3:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `sess_abc:11-15` | 闭区间 `[11,15]`,展开 `11..15` |
| 列表 | `sess_abc:3,7,12` | 离散 index 列表 |

约束(不满足整次拒绝):**严格单调递增**(`15-11` / `12,7,3` 报错);**越界 / session 不存在** 报错。多个 `--source` 各落一条 `card_sessions`(`position_id` 指向新建的这个答案)。

### 文本字段:传文件 / stdin

`--issue`(create)、`--answer` / `--scope`(position)的值有三种传法,后两种**不经 shell / JSON 转义**,专门用于文本带引号、换行、`$`、反引号等特殊字符的情况:

| 写法 | 含义 |
|---|---|
| `--answer '<文本>'` | 行内字面值(默认) |
| `--answer @<path>` | 从文件读,**内容逐字节原样用**(不解析、不去空白) |
| `--answer @-` | 从 **stdin** 读(`@-` 整条命令只能出现一次) |

```bash
# 答案带特殊字符 → 写进文件再传,一个字符都不丢
memory.talk card position --card card_01jz8k2m --answer @answer.md --source sess_abc:11-15

# 或从 stdin 喂(剪贴板 / heredoc)
pbpaste | memory.talk card position --card card_01jz8k2m --answer @-
```

> 值本身就以 `@` 开头时,改用 `@<file>` / `@-` 传(文件内容原样读入,不会被再解释成路径)。

### 输出 — Markdown(默认)

````markdown
ok: `pos_01jzr5kq` (answer) under `card_01jz8k2m`
````

错误(到 stderr,exit 1):

````markdown
**error:** index 99 out of range for session `sess_abc`
````

### 输出 — JSON(`--json`)

```json
{"status": "ok", "card_id": "card_01jz8k2m", "position_id": "pos_01jzr5kq"}
```

返回的 `position_id` 就是以后 `review` 的对象。

### 副作用

- 在 `<card>` 下落一个 Position:`claim`(内联)+ `up/down/neutral_count` 初始化为 0 + `scope`(默认 `''`)。**不算 credence**(读时现算)。
- 每个 `--source` 落一条 `card_sessions`(`card_id` + `session_id` + `position_id` + `indexes`);校验 indexes 不越界,失败整条不落库。
- 文件罐:`positions/<pid>.json`(答案 `claim` 不可变);计数 / `scope` / 出处是 SQLite 派生运行态。详见 [`../../structure/v4/filesystem.md`](../../structure/v4/filesystem.md)。
- **不动卡上其它 Position**(append-only,新增不覆盖)。

### 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `--card` 指向的卡不存在 | `error: card 'card_xxx' not found`,exit 1 |
| `--answer` 缺失 / 空 | `error: --answer required`,exit 1 |
| `--source` 的 session 不存在 | `error: session 'sess_xxx' not found`,exit 1 |
| `--source` 的 indexes 越界 / 非单调 | `error: index N out of range ...` / `indexes must be monotonically increasing`,exit 1 |
| 显式 `--position_id` 前缀错 / 已存在 | `error: invalid position_id prefix` / `... already exists`,exit 1 |

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
| 建一个新问题(卡) | `card create --issue '<Q>'` |
| 给问题加一个答案 | `card position --card <cid> --answer '<A>' [--source ...]` |
| 看一张卡的所有答案 / 当下答案 | `card view <card_id>` |
| 对某个答案顶 / 踩 / 中立 | `review <position_id> <+1\|0\|-1> --cite ...` |
| 按相关度找卡 | `search <query>`(沿用 v3) |
| hook 阶段无意识召回 | `recall <session_id> <prompt>` |
| 连两张卡(IBIS 边) | `card-links`(API,见 [`../../api/v4/card-links.md`](../../api/v4/card-links.md)) |

> **改主意 ≠ 改卡**:答案错了不改 `claim`,而是 `card position --card <同一卡>` 加一个新答案 + `review <旧pid> -1` 踩旧的;credence 现算会把新答案抬上来,旧答案留作认知史。
