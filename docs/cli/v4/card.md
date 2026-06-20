# card

v4 卡的**写入**入口(给卡加答案 / 表态 / 连边)。一张卡 = 一个问题(Issue)+ 若干答案(Position),Card 和 Position 是两个对象。

> **问题(卡)本身不在这里建** —— 它由 [`session mark`](session.md#session-mark) 里的 `#…？` 在读 session 时**自动建 / 关联**(`#…？` miss = 新卡、hit = 连老卡;见 [生命周期 §1](../../works/v4/card-lifecycle.md))。`card` 命令组管的是对**已有卡**的写:加答案、顶踩、连边。

```
memory.talk card
├── position --card <cid> --claim '<答案>' [--source <sid>:<idx> ...] [--scope '<场景>'] [--json]
├── review --target <card#p<n> | card#l<n>> --argument <+1|0|-1> --cite <sid>:<idx> [--comment '<一句话>'] [--review_id <id>] [--json]
└── link --card <cid> --type <type> --target <id> --claim '<这条边为什么成立>' [--source <sid>:<idx> ...] [--json]   # 卡间 IBIS 边(受治理);看边走 read
```

**读**一张卡(问题 + 它所有答案 + 边 + 出处)走 [`read <card_id>`](read.md),读单条边走 [`read card_xxx#l1`](read.md);找卡走 [`search`](search.md);hook 召回走 [`recall`](recall.md);**建问题(卡)走 [`session mark`](session.md#session-mark)**。

> **参数风格:除 `read` / `search` 用位置参数(裸 id / query)外,所有命令的参数都是命名 flag(`--xx`)。** `card` 不带子命令直接打印 help。设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## card position

给一张**已存在的卡**加一个答案候选(Position)。同一个问题下可以有多个答案,各自被顶踩、按现算 credence 竞争。

```bash
memory.talk card position --card <card_id> --claim '<答案文本>' \
    [--source <session_id>:<indexes> ...] [--scope '<场景>'] [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--card` | 是 | 给哪张卡(`card_<…>`)加答案;卡必须**已存在** |
| `--claim` | 是 | 答案文本(`claim`,内联在 Position 上,不单独建节点、不共享)。值支持 `@<file>` / `@-` |
| `--source` | 否,可多次 | **答案的出处**:`<session_id>:<indexes>`,每个落一条 `position_sessions`(答案从哪几轮 `indexes` 长出来)。支持多 session(多次 `--source`) |
| `--scope` | 否 | **这个答案(Position)的**适用场景描述(`scope` 是 **Position 字段**,软提示、非门禁;负边界如「别用于育儿」写进这句)。值支持 `@<file>` / `@-` |

> **Position 没有独立 id**:它是所属卡的附属,寻址 `<card_id>#p<n>`(`p` + 卡内递增序号,跟 mark `<session_id>#m<n>` 一个路子)。序号由卡自动分配(本卡第几个答案 → `p1`/`p2`…),不由客户端指定。

详细字段语义见 [`../../structure/v4/card.md`](../../structure/v4/card.md)。

### `--source` 语法 / indexes

每个 `--source` 形如 `<session_id>:<indexes>`,`indexes` 语法沿用 v3:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `sess_abc:11-15` | 闭区间 `[11,15]`,展开 `11..15` |
| 列表 | `sess_abc:3,7,12` | 离散 index 列表 |

约束(不满足整次拒绝):**严格单调递增**(`15-11` / `12,7,3` 报错);**越界 / session 不存在** 报错。多个 `--source` 各落一条 `position_sessions`(`position` = 新建答案在卡内的 `p<n>`,`indexes` 必填、`mark` 可选)。

### 文本传文件 / stdin

文本类 flag 的值——`--claim` / `--scope`(position)、`--claim`(link)、`--comment`(review)——都有三种传法,后两种**不经 shell / JSON 转义**,专门用于内容带引号、换行、`$`、反引号等特殊字符的情况:

| 写法 | 含义 |
|---|---|
| `--claim '<文本>'` | 行内字面值(默认) |
| `--claim @<path>` | 从文件读,**内容逐字节原样用**(不解析、不去空白) |
| `--claim @-` | 从 **stdin** 读(`@-` 整条命令只能出现一次) |

```bash
# 答案带特殊字符 → 写进文件再传,一个字符都不丢
memory.talk card position --card card_01jz8k2m --claim @answer.md --source sess_abc:11-15
# 或从 stdin 喂
pbpaste | memory.talk card position --card card_01jz8k2m --claim @-
```

> 文本本身就以 `@` 开头时,改用 `@<file>` / `@-` 传(文件内容原样读入,不会被再解释成路径)。

### 输出 / 副作用 / 错误

输出 `{"status":"ok","card_id":…,"position":"p1"}`(`position` 就是以后 `card review` 的对象,寻址 `card_xxx#p1`)。副作用:落一个 Position(`claim` 内联,`up/down/neutral_count` 初始化 0,`scope` 默认 `''`;**不算 credence**,读时现算)+ 每个 `--source` 落一条 `position_sessions` + `positions/p<n>.json`(文件名 = 卡内序号,`claim` 不可变);**不动卡上其它 Position**(append-only)。错误:`--card` 卡不存在 / `--claim` 空 / `--source` 越界·非单调 → 报错 exit 1。

## card review

对一个**可治理对象**的"回帖"——表态它对不对:**支持(+1)、中立(0)、反对(−1)**,附带某次 session 的证据 rounds 和一句说明。沿用 v3 review,target 从整张卡**下放到 Position 或 CardLink**;`argument ≠ 0` 的 review 就是一条 **IBIS Argument**(顶 = pro / 踩 = con)。

```bash
memory.talk card review --target <card_xxx#p<n> | card_xxx#l<n>> --argument <+1|0|-1> --cite <session_id>:<indexes> [--comment '<一句话>'] [--review_id <id>] [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--target` | 是 | 被表态的对象,寻址 `card_xxx#p<n>`(Position 答案)**或** `card_xxx#l<n>`(CardLink 边)。**一个 flag,前缀分片告诉 kind**(`#p` → position、`#l` → link);`target_kind` 服务端从分片派生 |
| `--argument` | 是 | `+1` 支持(顶) / `0` 中立 / `-1` 反对(踩)。就是 review 的 `argument` 字段;其它值报错。对 Position = 「这答案对不对」,对 Link = 「这条边成不成立」 |
| `--cite` | 是 | 证据:`<session_id>:<indexes>`,**单 session**(一次表态来自一次具体对话);indexes 语法同 [#--source-语法--indexes](#--source-语法--indexes) |
| `--comment` | 否 | 一句话归因;`argument=0` 时强烈建议填。值支持 `@<file>` / `@-`(见 [#文本传文件--stdin](#文本传文件--stdin)) |
| `--review_id` | 否 | 不提供则自动生成 `review_<ULID>` |

> **`--cite`(review)vs `--source`(position / link)**:都填 `<session_id>:<indexes>`,但 `--cite` 是这次**表态的证据**(单 session,落 `reviews`);`--source` 是 Position / Link 的**出处**(可多 session,落 `position_sessions` / `link_sessions`)。两者都是 round 级 `indexes`,跟 card→session 的 `card_sessions`(经 mark)无关。
>
> 一条 review 只挂**单 session**;同一 `(card_id, target, session_id)` **可有多条**(早期反对、深入后转支持),由 `indexes` 区分,**不去重**。完整字段语义见 [`../../structure/v4/review.md`](../../structure/v4/review.md)。

### 副作用

- 校验 `--target`(`card_xxx#p<n>` 那张卡有第 n 个 Position,或 `card_xxx#l<n>` 那张卡有第 n 条 Link)存在、`session_id` 存在且 `indexes` 不越界、`argument ∈ {-1,0,1}` → 任一失败不落库。
- **累加该 target 的计数**(原子 upsert,按 `target_kind` 落 `positions` 或 `card_links`):`+1`→`up_count++` / `-1`→`down_count++` / `0`→`neutral_count++`。
- **不写 credence**——credence 读 / 排序 / 过滤时按 `up − down`(或 Wilson)现算,没有要 bump 的列(Position 和 Link 都没有)。
- 落 `reviews` 表(`card_id` + `target`(`p<n>` / `l<n>`)+ `target_kind` + `session_id` + `indexes` + `argument` + `comment`),沿用 v3 review 的 canonical;review **不进向量索引**。

### 中立(`--argument 0`)堆多了 → 可能衍生新 Position

一批中立 = 证据相关但不站现有任何答案的队,可能在为一个**还没说出来的答案**背书。可**离线**(人 / LLM 判)把它们聚类、`card position` 提一个新答案、再把这些 review 以 `+1` 重挂过去。**不自动**触发,见 [`../../works/v4/card.md`](../../works/v4/card.md#3-第二推credence--现算的质量分相关性只在召回时算)。

### 读取 / 推荐姿势

review **不单独 read**——在 [`read <card_id>`](read.md) 的每个 Position / Link 块以计数体现,或 [`read card_xxx#p1`](read.md#card_p--单个答案--它的-review) / `read card_xxx#l1` 看某 Position / 某边的全部 review。

```bash
memory.talk card review --target card_01jz8k2m#p1 --argument +1 --cite "$SID:20-25" --comment '再次确认,简洁版接住了'
memory.talk card review --target card_01jz8k2m#p2 --argument -1 --cite "$SID:3-8"  --comment '纯简洁漏了调试细节'
memory.talk card review --target card_01jz8k2m#l1 --argument +1 --cite "$SID:30-34" --comment '这条 specializes 边确实成立,两卡同一套 auth'
```

## card link

卡与卡之间的 **IBIS 边**(`card_links`,列是 `card_id`(主体)+ `target_id`,**没有对称的 from/to**)。一条边**本身就是一个主张**(受治理对象,有 `claim` / 顶踩 / 现算 credence / 证据 / 可 review),寻址 `<card_id>#l<n>`。`card link` **直接建一条边**:主体卡 `--card`(= `card_id`,`card_<…>`);`--target`(= `target_id`)一般是另一张卡,只有 `suggested_by` 允许指向一个答案(`card_<…>#p<n>`);`--claim` 写**这条边为什么成立**。**看一张卡的边走 [`read <card_id>`](read.md)(返回 out / in 两向,各带 claim + 现算 credence),读单条边走 [`read card_xxx#l<n>`](read.md)——边不多,不单设 list。** 调 [`POST /v4/cards/{card_id}/links`](../../api/v4/card-links.md);字段语义见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。

```bash
memory.talk card link --card <card_id> --type <type> --target <target_id> --claim '<这条边为什么成立>' [--source <session_id>:<indexes> ...] [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--card` | 是 | 主体卡(谁的边),`card_<…>`,**已存在** |
| `--type` | 是 | 边类型(下表五类型) |
| `--target` | 是 | 对端 `card_<…>`,或(仅 `suggested_by`)某答案 `card_<…>#p<n>`;`#p` 分片 → `target_type=position` |
| `--claim` | **是** | **这条边为什么成立**(关系断言 / 理由)。内联在边上、create 即冻(append-only)。值支持 `@<file>` / `@-`(见 [#文本传文件--stdin](#文本传文件--stdin)) |
| `--source` | 否,可多次 | **边的出处**:`<session_id>:<indexes>`,每个落一条 `link_sessions`(这条边从哪几轮 `indexes` 观察出来)。支持多 session |

| type | 含义 | 方向 |
|---|---|---|
| `specializes` | from 是 target 的更窄版(子问题,DAG 非树) | 有向 |
| `suggested_by` | from 被 target 引出来(出处 / 因果);target 可为 `card_…#p<n>`(Position) | 有向 |
| `questions` | from 质疑 target 的前提 / 框架 | 有向 |
| `replaces` | from 重述并取代 target(**保留历史**,不删 target) | 有向 |
| `related` | 兜底泛关联 | 无向 |

- 同一 `(card, type)` 下可挂多条(如 `specializes` 多父;A 同时特化 B 和 C 合法)—— **存在即合理**,各边各自成立、不竞争;低 credence 的边 read / recall 时淡出。
- **不重边**:UNIQUE `(card, type, target)` —— 同主体同类型同对端只一条。改主意是**踩它**(`card review --target card_xxx#l<n> --argument -1`,credence 现算掉下去 → 隐藏)或**加反向 `replaces` 边**,不是再建同边。
- `--target` 是 `card_<…>` 或 `card_<…>#p<n>`(后者 `#p` 分片 → `target_type=position`),自动落进 `card_links` 表,便于按对端类型过滤。
- `related` 无向:写时规范化两端顺序只存一遍(`--card A … --target B` 与 `--card B … --target A` 等价)。
- **不校验 `--target` 是否存在**:SQLite 派生索引,容忍悬挂引用,从不加 FOREIGN KEY。
- `issue` 层的 `replaces`(问题取代问题)≠ Position 层的 `forked_from`(答案分叉),别混。

### 输出 / 副作用

输出 `{"status":"ok","card_id":…,"link":"l1","type":…,"target_id":…,"target_type":…}`(`link` = `l<n>`,就是以后 `card review --target card_xxx#l<n>` 的对象)。副作用:落一条 CardLink(`claim` 内联,`up/down/neutral_count` 初始化 0;**不算 credence**,读时现算)+ 每个 `--source` 落一条 `link_sessions` + `links/l<n>.json`(文件名 = 卡内序号,边核不可变);`cards.link_count++`。

错误:`--card` 卡不存在 / `--type` 不在五类型 / `--target` 非 `card_…`/`card_…#p`(或 `#p` 分片用在非 `suggested_by`)/ `--claim` 空 / 同边已存在(违反 UNIQUE)/ `--source` 越界·非单调 → 报错 exit 1。

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 建一个新问题(卡) | 在 [`session mark`](session.md#session-mark) 里写 `#…？`(卡由 mark 自动建,无 `card create`) |
| 给问题加一个答案 | `card position --card <cid> --claim '<A>' [--source ...]` |
| 对某个答案 / 某条边顶 / 踩 / 中立 | `card review --target <card_xxx#p<n> \| card_xxx#l<n>> --argument <+1\|0\|-1> --cite ...` |
| 连两张卡(IBIS 边,带理由) | `card link --card <cid> --type <type> --target <id> --claim '<为什么>'` |
| **看一张卡 / 它所有答案 / 当下答案** | `read <card_id>`(见 [read.md](read.md)) |
| 看单条边 / 单个答案 | `read card_xxx#l<n>` / `read card_xxx#p<n>` |
| 按相关度找卡 | `search <query>` |
| hook 阶段无意识召回 | `recall --session <sid> --prompt '<p>'` |

> **改主意 ≠ 改卡**:答案错了不改 `claim`,而是 `card position --card <同一卡> --claim '<新答案>'` 加一个新答案 + `card review --target card_xxx#p<旧n> --argument -1` 踩旧的;credence 现算会把新答案抬上来,旧答案留作认知史。**边错了同理**:不删边,而是 `card review --target card_xxx#l<n> --argument -1` 踩它(credence 掉下去 → 隐藏)或加一条反向 `replaces` 边。
