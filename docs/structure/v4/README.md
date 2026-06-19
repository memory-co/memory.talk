# Structure (v4)

v4 的数据模型 —— 描述对象 schema、字段语义、磁盘 / 数据库布局。

v4 是 **card 的另一代**:一张卡不再是「一句陈述」,而是「**一个问题(Issue)+ 它的若干答案(Position)**」,所有卡连成一张**被治理的问题图**(IBIS + 现算 credence 投票)。机制 / 设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)。

- CLI 契约见 [`../../cli/v4/`](../../cli/v4/)
- HTTP 契约见 [`../../api/v4/`](../../api/v4/)
- 机制 / 设计决策见 [`../../works/v4/card.md`](../../works/v4/card.md)、写路径前端见 [`../../works/v4/session-annotation.md`](../../works/v4/session-annotation.md)

## 对象清单

| 对象 | 形态 | 文档 |
|---|---|---|
| Card ≡ Issue | 一张卡 = 一个**问题**;图节点 + 检索单元 | [card.md](card.md) |
| Position | 卡底下的一个**候选答案**;被顶/踩、按现算 credence 竞争 | [card.md](card.md) |
| Review | append-only,对 **Position** 的一次表态(`argument` ±1/0 + 证据 indexes) | [review.md](review.md) |
| CardLink | card↔card 的 IBIS 有向边(specializes / suggested_by / ...) | [card-link.md](card-link.md) |
| CardSession | card↔session 出处(哪个 session 启发了这张卡 / 哪个答案) | [card-session.md](card-session.md) |

> **沿用 v3、本目录不复制**:Session / Search-Result / Recall-Event / Settings 等基础设施在 v4 没变,直接看 [`../../structure/v3/`](../../structure/v3/)。v4 只重写「卡子系统」这一层(上面 5 个对象)。

## ID 前缀

| 对象 | 前缀 | 示例 |
|---|---|---|
| Card | `card_` | `card_01jz8k2m...` |
| Position | `pos_` | `pos_01jzr5kq...` |
| Review | `review_` | `review_01jzp3nq...` |
| Session | `sess_` | `sess_187c6576-...`(沿用 v3) |

前缀 = 类型,CLI / API 按前缀零成本判型分发。`card_` 前缀是 v3 card 改名 `insight_` 之后**腾出来复用**的(见 [#与-v3--insight-的关系](#与-v3--insight-的关系))。

## 一张卡长什么样

```
Card (= Issue, card_xxx)  "用户偏好什么回答风格?"
├── Position pos_a  "简洁优先"          up 7 / down 1 / neutral 2
├── Position pos_b  "复杂问题要详细"     up 3 / down 0 / neutral 1
└── Position pos_c  "看场景"            up 1 / down 0 / neutral 0  (forked_from pos_a)

边(不内联,在 card_links):  card_xxx --specializes--> card_yyy
出处(不内联,在 card_sessions): card_xxx ←── sess_def #11-15 启发了 pos_a
表态(不内联,在 reviews):      review_* --argument=+1--> pos_a
```

**「当下用哪个答案」不是存字段**:召回时取 credence(= `up_count`/`down_count` **现算**的校验分,平手按最近更新)最高的 Position。没有 `accepted` 标志,也没有 open/closed 状态 —— 一个 Issue 允许多个 Position 长期并存竞争。

## 磁盘布局速查

完整清单(SQLite 表 / LanceDB collection / 文件罐 / 双写关系)见 [filesystem.md](filesystem.md)。速查:

```
~/.memory.talk/
├── memory.db                            # SQLite,详见各 md 的"存储"小节
├── cards/<bucket>/<card_id>/
│   ├── card.json                        # canonical:issue + created_at(问题不可变)
│   └── positions/<pid>.json             # canonical:claim + created_at(答案核不可变)
├── insights/<bucket>/<insight_id>/...   # v3 card 改名而来,只读(见下)
├── vectors/                             # LanceDB:cards(embed issue) / insights / rounds
└── sessions/ ...                        # 沿用 v3
```

`<bucket>` = `card_id` 去掉 `card_` 前缀后的前 2 字符(代码里 `card_id[5:7]`)。

**SQLite 是派生索引**(计数 / 现算排序 / 关系查询 / DSL 过滤);**文件罐是 canonical**(可移植 / 审计,崩了能重建 SQLite);**LanceDB 是检索召回的唯一来源**(embed `issue`)。

## append-only 不变性

v4 的卡子系统遵守**三条不变性**:

1. **不可变核 create 即冻** —— Card 的 `issue`、Position 的 `(card_id, claim, created_at)` 一旦写入不可改;canonical 落文件罐。要「翻新」只能**新增一个竞争 Position**(同卡内)或**新建一张卡**(`replaces` 边指回),不改旧的。
2. **计数 / 治理是 runtime 状态,不属于不可变核** —— `up_count` / `down_count` / `neutral_count` 由 review 落库自动累加;`scope` / `forked_from_position_id` 是运行态。读时跟不可变核合并返回,写入路径独立。
3. **Position 只增不改不删(append-only)** —— 答案变了不覆盖、不归档:新增一个竞争 Position,旧的被踩则 credence 现算掉下去、自然不再被注入,但仍可查。认知史落在 `reviews` 日志 + 并存的旧 Position 上,**不靠状态位**(没有 `change_state` / `superseded_by`)。

由这三条联合保证:**lineage 自然成 DAG**(Position / Card append-only + `forked_from_position_id` / `card_links` 只能引用已存在的对象 → 物理时序排除环)。

## 「现算」而非「存储」的几个量

v4 把一批可派生的量留成**读时现算**、不落列:

| 量 | 怎么来 |
|---|---|
| `credence`(校验分) | `f(up_count, down_count)`,排序时算 |
| 「当下答案」 | 召回时取 credence 最高的 active Position(无 `accepted` 字段) |
| 「相不相关」 | 召回那一刻向量 + FTS 现算 |

为什么这样切(删 momentum / 时间维 / accepted / credence 列)见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 / §5 / §12。

## 与 v3 / insight 的关系

v4 不改 v3 的卡,而是**另起一代**。v3 现有的那套卡(`insight` 字段 + 论坛动力学 stats)整体**改名成 `insight`、数据保留、只读可搜**,把 `card` / `card_` / `reviews` 这些名字腾给 v4。

| | v3 card → 改名后 insight | v4 card |
|---|---|---|
| 一张卡是 | 一句 `insight` 陈述 | 一个 **Issue(问题)+ 若干 Position(答案)** |
| 哪个对 | 整卡一个立场,沉浮三轴算 | 同卡多答案各自被顶踩,现算 credence 竞争 |
| 关联 | `source_cards`(创建即冻) | `card_links`(card↔card)+ `card_sessions`(card↔session) |
| 命运 | 只读、慢慢下掉(可投影进 v4 图) | 新主路径 |

v4 与 insight **物理隔离**(不同表、不同 collection、不同前缀),互不干扰共存。迁移见 [`../../works/v4/card.md`](../../works/v4/card.md) §9。

## 卡子系统跟 v3 的对象级差异

| | v3(card,即将改名 insight) | v4 |
|---|---|---|
| 主对象 | card, review | **card(Issue), position, review, card_link, card_session** |
| 卡的粒度 | 一句陈述 | 一个问题 + 多个答案候选 |
| 顶踩挂在 | 整张卡(`card_stats`) | **每个 Position** 各自计数 |
| 质量分 | `card.stats` 6 计数 + 沉浮公式 | `up/down/neutral_count` 三计数;credence 现算 |
| 关联 | `source_cards`(card→card,内联) | `card_links`(card↔card)+ `card_sessions`(card↔session),都独立表、可 join |
| 沉浮 / engagement | `read_count` / `recall_count` + 沉浮公式 | **全删** —— 相关性只在召回时检索现算,不回写 |
| 状态 | 无显式状态(沉浮算) | 无状态机(`change_state` / `accepted` 都不要);Position append-only |
