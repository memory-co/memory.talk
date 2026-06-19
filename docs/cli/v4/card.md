# card

v4 卡的**写入**入口。一张卡 = 一个问题(Issue)+ 若干答案(Position),Card 和 Position 是两个对象。`card` 是命令组,所有卡相关写操作都是它的子命令:

```
memory.talk card
├── create --issue '<问题>' [--card_id <id>] [--json]
├── position --card <cid> --answer '<答案>' [--source <sid>:<idx> ...] [--scope '<场景>'] [--position_id <id>] [--json]
├── review --position <pid> --vote <+1|0|-1> --cite <sid>:<idx> [--comment '<一句话>'] [--review_id <id>] [--json]
└── link create --from <cid> --type <type> --target <id>  |  link list --card <cid>  [--json]
```

**读**一张卡(问题 + 它所有答案 + 边 + 出处)走 [`read <card_id>`](read.md);找卡走 [`search`](search.md);hook 召回走 [`recall`](recall.md)。

> **参数风格:除 `read` / `search` 用位置参数(裸 id / query)外,所有命令的参数都是命名 flag(`--xx`)。** `card` 不带子命令直接打印 help。设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## card create

建一张卡——只立一个问题,不带答案。一张没有任何 Position 的卡是合法的(就是个还在等答案的问题);答案另走 [`card position`](#card-position)。

```bash
memory.talk card create --issue '<问题文本>' [--card_id <id>] [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--issue` | 是 | 问题文本(`issue`),也是 embedding 锚点(检索撞的就是它)。值支持 `@<file>` / `@-`(见 [#文本传文件--stdin](#文本传文件--stdin)) |
| `--card_id` | 否 | 显式指定 id;不提供则自动生成 `card_<ULID>` |

输出 `{"status":"ok","card_id":"card_…"}`。副作用:落 `cards`(`issue` + `created_at`)+ 写向量库;`cards/<bucket>/<card_id>/card.json`(问题不可变);**不落任何 Position**。错误:`--issue` 缺失 → `--issue required`;`--card_id` 前缀错 / 已存在 → 报错 exit 1。

## card position

给一张**已存在的卡**加一个答案候选(Position)。同一个问题下可以有多个答案,各自被顶踩、按现算 credence 竞争。

```bash
memory.talk card position --card <card_id> --answer '<答案文本>' \
    [--source <session_id>:<indexes> ...] [--scope '<场景>'] [--position_id <id>] [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--card` | 是 | 给哪张卡(`card_<…>`)加答案;卡必须**已存在** |
| `--answer` | 是 | 答案文本(`claim`,内联在 Position 上,不单独建节点、不共享)。值支持 `@<file>` / `@-` |
| `--source` | 否,可多次 | 出处:`<session_id>:<indexes>`,每个落一条 `card_sessions`。支持多 session(多次 `--source`) |
| `--scope` | 否 | **这个答案(Position)的**适用场景描述(`scope` 是 **Position 字段**,软提示、非门禁;负边界如「别用于育儿」写进这句)。值支持 `@<file>` / `@-` |
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

文本类 flag 的值——`--issue`(create)、`--answer` / `--scope`(position)、`--comment`(review)——都有三种传法,后两种**不经 shell / JSON 转义**,专门用于内容带引号、换行、`$`、反引号等特殊字符的情况:

| 写法 | 含义 |
|---|---|
| `--answer '<文本>'` | 行内字面值(默认) |
| `--answer @<path>` | 从文件读,**内容逐字节原样用**(不解析、不去空白) |
| `--answer @-` | 从 **stdin** 读(`@-` 整条命令只能出现一次) |

```bash
# 答案带特殊字符 → 写进文件再传,一个字符都不丢
memory.talk card position --card card_01jz8k2m --answer @answer.md --source sess_abc:11-15
# 或从 stdin 喂
pbpaste | memory.talk card position --card card_01jz8k2m --answer @-
```

> 文本本身就以 `@` 开头时,改用 `@<file>` / `@-` 传(文件内容原样读入,不会被再解释成路径)。

### 输出 / 副作用 / 错误

输出 `{"status":"ok","card_id":…,"position_id":"pos_…"}`(`position_id` 就是以后 `card review` 的对象)。副作用:落一个 Position(`claim` 内联,`up/down/neutral_count` 初始化 0,`scope` 默认 `''`;**不算 credence**,读时现算)+ 每个 `--source` 落一条 `card_sessions` + `positions/<pid>.json`(`claim` 不可变);**不动卡上其它 Position**(append-only)。错误:`--card` 卡不存在 / `--answer` 空 / `--source` 越界·非单调 / `--position_id` 前缀错·已存在 → 报错 exit 1。

## card review

对一个**答案(Position)**的"回帖"——表态它对不对:**支持(+1)、中立(0)、反对(−1)**,附带某次 session 的证据 rounds 和一句说明。沿用 v3 review,只把 target 从整张卡**下放到 Position**;`argument ≠ 0` 的 review 就是一条 **IBIS Argument**(顶 = pro / 踩 = con)。

```bash
memory.talk card review --position <position_id> --vote <+1|0|-1> --cite <session_id>:<indexes> [--comment '<一句话>'] [--review_id <id>] [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--position` | 是 | 被表态的答案,必须是 `pos_<…>`。**target 是 Position,不是 card** |
| `--vote` | 是 | `+1` 支持(顶) / `0` 中立 / `-1` 反对(踩)。落成 review 的 `argument`;其它值报错 |
| `--cite` | 是 | 证据:`<session_id>:<indexes>`,**单 session**(一次表态来自一次具体对话);indexes 语法同 [#--source-语法--indexes](#--source-语法--indexes) |
| `--comment` | 否 | 一句话归因;`argument=0` 时强烈建议填。值支持 `@<file>` / `@-`(见 [#文本传文件--stdin](#文本传文件--stdin)) |
| `--review_id` | 否 | 不提供则自动生成 `review_<ULID>` |

> **`--cite`(review)vs `--source`(position)**:都填 `<session_id>:<indexes>`,但 `--cite` 是这次**表态的证据**(单 session);`--source` 是答案的**出处**(可多 session,落 `card_sessions`)。
>
> 一条 review 只挂**单 session**;同一 `(position_id, session_id)` **可有多条**(早期反对、深入后转支持),由 `indexes` 区分,**不去重**。完整字段语义见 [`../../structure/v4/review.md`](../../structure/v4/review.md)。

### 副作用

- 校验 `position_id` 存在、`session_id` 存在且 `indexes` 不越界、`argument ∈ {-1,0,1}` → 任一失败不落库。
- **累加该 Position 的计数**(原子 upsert):`+1`→`up_count++` / `-1`→`down_count++` / `0`→`neutral_count++`。
- **不写 credence**——credence 读 / 排序时按 `up − down`(或 Wilson)现算,没有要 bump 的列。
- 落 `reviews` 表(`position_id` + 冗余 `card_id` + `session_id` + `indexes` + `argument` + `comment`),沿用 v3 review 的 canonical;review **不进向量索引**。

### 中立(`--vote 0`)堆多了 → 可能衍生新 Position

一批中立 = 证据相关但不站现有任何答案的队,可能在为一个**还没说出来的答案**背书。可**离线**(人 / LLM 判)把它们聚类、`card position` 提一个新答案、再把这些 review 以 `+1` 重挂过去。**不自动**触发,见 [`../../works/v4/card.md`](../../works/v4/card.md#3-第二推credence--现算的质量分相关性只在召回时算)。

### 读取 / 推荐姿势

review **不单独 read**——在 [`read <card_id>`](read.md) 的每个 Position 块以计数体现,或 [`read <position_id>`](read.md#pos_--单个答案--它的-review) 看某答案的全部 review。

```bash
memory.talk card review --position pos_01jzp3nq --vote +1 --cite "$SID:20-25" --comment '再次确认,简洁版接住了'
memory.talk card review --position pos_01jz0xnq --vote -1 --cite "$SID:3-8"  --comment '纯简洁漏了调试细节'
```

## card link

卡与卡之间的 **IBIS 边**(`card_links`)——问题图的关联主干。边连的是**卡(问题)**:主体 `--from`(`card_<…>`);`--target` 一般是另一张卡,只有 `suggested_by` 允许指向一个答案(`pos_<…>`,「这个答案勾出了那个新问题」)。调 [`POST /v4/cards/{card_id}/links`](../../api/v4/card-links.md);字段语义见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。

### card link create

```bash
memory.talk card link create --from <from_card_id> --type <type> --target <target_id> [--json]
```

| type | 含义 | 方向 |
|---|---|---|
| `specializes` | from 是 target 的更窄版(子问题,DAG 非树) | 有向 |
| `suggested_by` | from 被 target 引出来(出处 / 因果);target 可为 `pos_` | 有向 |
| `questions` | from 质疑 target 的前提 / 框架 | 有向 |
| `replaces` | from 重述并取代 target(**保留历史**,不删 target) | 有向 |
| `related` | 兜底泛关联 | 无向 |

- 同一 `(from, type)` 下可挂多条(如 `specializes` 多父)。
- `related` 无向:写时规范化两端顺序只存一遍(`--from A … --target B` 与 `--from B … --target A` 等价)。
- **不校验 `target` 是否存在**:SQLite 派生索引,容忍悬挂引用,从不加 FOREIGN KEY。
- `issue` 层的 `replaces`(问题取代问题)≠ Position 层的 `forked_from_position_id`(答案分叉),别混。

错误:`--from` 卡不存在 / `--type` 不在五类型 / `--target` 前缀错(非 `card_`·`pos_`,或 `pos_` 用在非 `suggested_by`)/ 同边已存在 → 报错 exit 1。

### card link list

列一张卡相关的边——**指出去的**(本卡为主体)+ **指过来的**(别的卡指本卡)。

```bash
memory.talk card link list --card <card_id> [--json]
```

```json
{
  "card_id": "card_01jz8k2m",
  "out": [{"type": "specializes", "target_id": "card_01jzsub"}],
  "in":  [{"type": "replaces", "from_card_id": "card_01jzold"}]
}
```

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 建一个新问题(卡) | `card create --issue '<Q>'` |
| 给问题加一个答案 | `card position --card <cid> --answer '<A>' [--source ...]` |
| 对某个答案顶 / 踩 / 中立 | `card review --position <pid> --vote <+1\|0\|-1> --cite ...` |
| 连两张卡(IBIS 边) | `card link create --from <cid> --type <type> --target <id>` |
| **看一张卡 / 它所有答案 / 当下答案** | `read <card_id>`(见 [read.md](read.md)) |
| 按相关度找卡 | `search <query>` |
| hook 阶段无意识召回 | `recall --session <sid> --prompt '<p>'` |

> **改主意 ≠ 改卡**:答案错了不改 `claim`,而是 `card position --card <同一卡> --answer '<新答案>'` 加一个新答案 + `card review --position <旧pid> --vote -1` 踩旧的;credence 现算会把新答案抬上来,旧答案留作认知史。
