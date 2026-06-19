# card

v4 卡的**写入**入口。一张卡 = 一个问题(Issue)+ 若干答案(Position),Card 和 Position 是两个对象,所以 `card` 拆成两条**写**命令:

```
memory.talk card
├── create '<问题>' [--card_id <id>] [--json]
│                                            # 建一张卡(只有问题;没答案也合法)
├── position <card_id> '<答案>' [--source <sid>:<indexes> ...] [--scope '<场景>'] [--position_id <id>] [--json]
│                                            # 给一张卡加一个答案(Position)
├── review <position_id> <+1|0|-1> --cite <sid>:<indexes> [--comment '<一句话>'] [--json]
│                                            # 对某个答案表态(顶/踩/中立),详见 review.md
└── link create <from> <type> <target> | link list <card>
                                             # 卡间 IBIS 边(card_links),详见 link.md
```

**读**一张卡(问题 + 它所有答案 + 边 + 出处)走 [`read <card_id>`](read.md);表态(顶/踩答案)走 [`card review`](review.md);找卡走 [`search`](search.md);hook 召回走 [`recall`](recall.md)。

> 主内容(问题 / 答案)走**位置参数**(跟 `card review <position_id> <argument>` 一致),不用同名 flag。`card` 是 group 命令,不带子命令直接打印 help。设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## card create

建一张卡——只立一个问题,不带答案。一张没有任何 Position 的卡是合法的(就是个还在等答案的问题);答案另走 [`card position`](#card-position)。

```bash
memory.talk card create '<问题文本>' [--card_id <id>] [--json]
```

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `<问题文本>` | 是 | 位置参数:问题(`issue`),也是 embedding 锚点(检索撞的就是它)。支持 `@<file>` / `@-`(见 [#文本传文件--stdin](#文本传文件--stdin)) |
| `--card_id` | 否 | 显式指定 id;不提供则自动生成 `card_<ULID>` |

### 输出

````markdown
ok: created `card_01jz8k2m`
````

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
| 问题文本缺失 / 空 | `error: issue text required`,exit 1 |
| `--card_id` 前缀错 / 已存在 | `error: invalid card_id prefix` / `... already exists`,exit 1 |

---

## card position

给一张**已存在的卡**加一个答案候选(Position)。同一个问题下可以有多个答案,各自被顶踩、按现算 credence 竞争。

```bash
memory.talk card position <card_id> '<答案文本>' \
    [--source <session_id>:<indexes> ...] \
    [--scope '<适用场景描述>'] \
    [--position_id <id>] \
    [--json]
```

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `<card_id>` | 是 | 位置参数:给哪张卡(`card_<…>`)加答案;卡必须**已存在** |
| `<答案文本>` | 是 | 位置参数:答案(`claim`),内联在 Position 上(不单独建节点、不共享)。支持 `@<file>` / `@-` |
| `--source` | 否,可多次 | 出处:`<session_id>:<indexes>`,每个落一条 `card_sessions`。支持多 session(多次 `--source`) |
| `--scope` | 否 | **这个答案(Position)的**适用场景描述(`scope` 是 **Position 字段**,软提示、非门禁;负边界如「别用于育儿」写进这句)。支持 `@<file>` / `@-` |
| `--position_id` | 否 | 显式指定 id;不提供则自动生成 `pos_<ULID>` |

详细字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### `--source` 语法 / indexes

每个 `--source` 形如 `<session_id>:<indexes>`,`indexes` 语法沿用 v3:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `sess_abc:11-15` | 闭区间 `[11,15]`,展开 `11..15` |
| 列表 | `sess_abc:3,7,12` | 离散 index 列表 |

约束(不满足整次拒绝):**严格单调递增**(`15-11` / `12,7,3` 报错);**越界 / session 不存在** 报错。多个 `--source` 各落一条 `card_sessions`(`position_id` 指向新建的这个答案)。

### 文本传文件 / stdin

问题(create)、答案、`--scope`(position)的文本值有三种传法,后两种**不经 shell / JSON 转义**,专门用于内容带引号、换行、`$`、反引号等特殊字符的情况:

| 写法 | 含义 |
|---|---|
| `'<文本>'` | 行内字面值(默认) |
| `@<path>` | 从文件读,**内容逐字节原样用**(不解析、不去空白) |
| `@-` | 从 **stdin** 读(`@-` 整条命令只能出现一次) |

```bash
# 答案带特殊字符 → 写进文件再传,一个字符都不丢
memory.talk card position card_01jz8k2m @answer.md --source sess_abc:11-15

# 或从 stdin 喂(剪贴板 / heredoc)
pbpaste | memory.talk card position card_01jz8k2m @-
```

> 文本本身就以 `@` 开头时,改用 `@<file>` / `@-` 传(文件内容原样读入,不会被再解释成路径)。

### 输出

````markdown
ok: `pos_01jzr5kq` (answer) under `card_01jz8k2m`
````

错误(到 stderr,exit 1):

````markdown
**error:** index 99 out of range for session `sess_abc`
````

```json
{"status": "ok", "card_id": "card_01jz8k2m", "position_id": "pos_01jzr5kq"}
```

返回的 `position_id` 就是以后 `review` 的对象。

### 副作用

- 在 `<card_id>` 下落一个 Position:`claim`(内联)+ `up/down/neutral_count` 初始化为 0 + `scope`(默认 `''`)。**不算 credence**(读时现算)。
- 每个 `--source` 落一条 `card_sessions`(`card_id` + `session_id` + `position_id` + `indexes`);校验 indexes 不越界,失败整条不落库。
- 文件罐:`positions/<pid>.json`(答案 `claim` 不可变);计数 / `scope` / 出处是 SQLite 派生运行态。详见 [`../../structure/v4/filesystem.md`](../../structure/v4/filesystem.md)。
- **不动卡上其它 Position**(append-only,新增不覆盖)。

### 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `<card_id>` 指向的卡不存在 | `error: card 'card_xxx' not found`,exit 1 |
| 答案文本缺失 / 空 | `error: answer text required`,exit 1 |
| `--source` 的 session 不存在 | `error: session 'sess_xxx' not found`,exit 1 |
| `--source` 的 indexes 越界 / 非单调 | `error: index N out of range ...` / `indexes must be monotonically increasing`,exit 1 |
| `--position_id` 前缀错 / 已存在 | `error: invalid position_id prefix` / `... already exists`,exit 1 |

---

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 建一个新问题(卡) | `card create '<Q>'` |
| 给问题加一个答案 | `card position <card_id> '<A>' [--source ...]` |
| **看一张卡 / 它所有答案 / 当下答案** | `read <card_id>`(见 [read.md](read.md)) |
| 对某个答案顶 / 踩 / 中立 | `card review <position_id> <+1\|0\|-1> --cite ...` |
| 按相关度找卡 | `search <query>` |
| hook 阶段无意识召回 | `recall <session_id> <prompt>` |
| 连两张卡(IBIS 边) | `card link create <from> <type> <target>`(见 [link.md](link.md)) |

> **改主意 ≠ 改卡**:答案错了不改 `claim`,而是 `card position <同一卡> '<新答案>'` 加一个新答案 + `card review <旧pid> -1` 踩旧的;credence 现算会把新答案抬上来,旧答案留作认知史。
