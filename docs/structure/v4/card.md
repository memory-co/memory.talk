# Card + Position

v4 的核心数据结构 —— 一张卡 = **一个 Card(问题,≡ Issue)+ 它底下若干 Position(候选答案)**。

- **Card** 是图节点 + 检索单元(embed `issue`)。**不可变核** create 即冻。
- **Position** 是被顶/踩、按现算 credence 竞争的那个东西。`claim`(答案文本)不可变;顶踩计数 / `scope` / 血缘是 runtime 状态。**Position 没有独立 `pos_` id** —— 它是卡的附属,寻址 `<card_id>#p<n>`(`p` + 卡内递增序号),跟 mark 寻址 `<session_id>#m<n>` 同构(见 [session-mark.md](session-mark.md))。

机制 / 设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md)(§2 问答化、§3 credence、§5 治理)。Review / CardLink / CardSession 各自独立,见 [review.md](review.md) / [card-link.md](card-link.md) / [card-session.md](card-session.md)。

## Schema

下面是 `read card_xxx`(`POST /v4/read`)响应里**合并后**的视图:Card + 它的 Position 列表(每个 Position 带现算 `credence` + 计数)。底层文件罐只存不可变核,计数 / 治理在 SQLite,详见 [#存储](#存储)。

```json
{
  "card_id": "card_01jz8k2m",
  "issue": "用户偏好什么回答风格?",
  "created_at": "2026-06-18T14:30:00Z",
  "positions": [
    {
      "card_id": "card_01jz8k2m",
      "position": "p1",
      "claim": "简洁优先 —— 默认给结论,展开按需",
      "up_count": 7,
      "down_count": 1,
      "neutral_count": 2,
      "credence": 6,
      "scope": "日常技术问答场景;面向有经验的用户。复杂决策题不适用——那种要展开。",
      "forked_from": null,
      "created_at": "2026-06-18T14:30:00Z"
    },
    {
      "card_id": "card_01jz8k2m",
      "position": "p2",
      "claim": "看场景 —— 简单题简洁,决策题详细",
      "up_count": 1,
      "down_count": 0,
      "neutral_count": 0,
      "credence": 1,
      "scope": "",
      "forked_from": "p1",
      "created_at": "2026-06-19T09:02:00Z"
    }
  ]
}
```

> `credence` 是**现算字段**(`f(up_count, down_count)`),read 响应里给出方便消费;它**不落库**(SQLite / 文件罐都没有这一列)。「当下用哪个答案」= credence 最高的 Position(此例 `card_01jz8k2m#p1`),无 `accepted` 标志。

## Card 字段

### 不可变核(create 即冻,canonical 在文件罐)

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 自动 | `card_<ULID>`,不提供则自动生成 |
| `issue` | string | 是 | 卡的那个**问题**(一句话);也是 embedding 锚点(进向量库) |
| `created_at` | string | 自动 | ISO 8601 |

> 卡↔卡的边(specializes / suggested_by / questions / replaces / related)**不内联**,单独存 `card_links`,见 [card-link.md](card-link.md)。一张**还没有任何 Position** 的 Card 是合法的 —— 它就是个「还在等答案的问题」,不必被「解决掉」,所以也**没有 open/closed 状态**。

### Runtime 计数(SQLite 实时维护,冗余缓存)

| 字段 | 类型 | 说明 |
|---|---|---|
| `position_count` | integer | 这张卡有几个 Position(答案);加答案时 +1。`0` = 还在等答案的问题 |
| `link_count` | integer | 这张卡作为主体(`from`)的 `card_links` 条数;建边时 +1 |

> 都是**冗余计数**——可由 `positions` / `card_links` 表 `COUNT(*)` 重算,缓存在卡上免 join。

## Position 字段

### 不可变核(create 即冻,canonical 在文件罐)

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 属于哪张卡(问题);`card_<...>` |
| `position` | string | 自动 | 卡内序号 `p<n>`(`p1`/`p2`…);**没有独立 `pos_` id**,寻址 = `{card_id}#{position}`(如 `card_01jz8k2m#p1`),跟 mark `<session_id>#m<n>` 同构 |
| `claim` | string | 是 | **答案文本**,内联在 Position 上(不单独建 Claim 节点、不跨 Position 共享) |
| `created_at` | string | 自动 | ISO 8601 |

### 校验轴 —— 顶踩计数(runtime,SQLite 实时维护)

| 字段 | 类型 | 说明 |
|---|---|---|
| `up_count` | integer | 收到的 `argument=+1`(顶 / 支持)review 数。对应 v3 的 `review_up` |
| `down_count` | integer | 收到的 `argument=−1`(踩 / 反对)review 数。对应 v3 的 `review_down` |
| `neutral_count` | integer | 收到的 `argument=0`(中立)review 数。对应 v3 的 `review_neutral` |
| `review_count` | integer | review 总数 = `up_count` + `down_count` + `neutral_count`。**冗余缓存**,免每次求和 |

这是 Position 上**唯一的质量轴**。沉默(没 review)和中立都不进 `up`/`down`,因此不影响 credence。中立堆多了可能触发离线衍生新 Position(机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 末)。

### 治理(runtime,SQLite 实时维护)

| 字段 | 类型 | 说明 |
|---|---|---|
| `scope` | string | **位** —— 一句话描述这个答案适用什么场景(自由文本软提示),可含「不适用于…」。**不是门禁**:召回时随答案一起喂给 LLM 当软提示,让模型自判语境;跨界默认放行。空串 = 没写 |
| `forked_from` | string\|null | **变** —— 信念分叉时记「从**本卡**哪个 Position 分出来」(血缘指针,保认知史);值是同卡内的 `p<n>`,或 `null`。Position 只从**自己这张卡**的另一个 Position 分叉 |

### 现算(不落库,read / 排序时算)

| 量 | 怎么算 | 说明 |
|---|---|---|
| `credence` | `f(up_count, down_count)` | 校验分:`up−down`,或带样本量的 Wilson 下界(10顶0踩 > 1顶0踩)。具体公式见 [`../../works/v4/card.md`](../../works/v4/card.md) §12 待定 |
| 「当下答案」 | 召回时取 credence 最高的 Position | 没有 `accepted` 字段;平手用最近更新(最后一条 review `created_at`)tiebreak |

## 存储

### 不可变核(文件罐)

```
cards/<bucket>/<card_id>/
├── card.json                    # canonical:issue + created_at(问题不可变)
└── positions/
    ├── p1.json                  # canonical:claim + created_at(答案核不可变),文件名 = p<n>
    └── p2.json
```

`<bucket>` = `card_id` ULID 部分前 2 字符(代码 `card_id[5:7]`,跳过 `card_` 前缀)。Position 文件放在所属卡目录下、按卡内序号 `p<n>` 命名 —— 一张卡 = 一个问题 + 它的答案们,物理聚在一起(跟 mark 的 `marks/m<n>.yaml` 同构)。

### Runtime state(SQLite)

```sql
-- 卡 = 问题(≡ Issue),图节点
CREATE TABLE cards (
  card_id        TEXT PRIMARY KEY,         -- card_<ulid>
  issue          TEXT NOT NULL,            -- 问题文本;检索锚点(进向量库)
  created_at     TEXT NOT NULL,
  position_count INTEGER NOT NULL DEFAULT 0,  -- 冗余:本卡 Position 数(加答案时 +1)
  link_count     INTEGER NOT NULL DEFAULT 0   -- 冗余:本卡作主体的 card_links 数(建边时 +1)
);

-- Position = 答案候选;被顶踩、按 credence 竞争的就是它。无独立 id:寻址 = card_id#position(p<n>)
CREATE TABLE positions (
  card_id        TEXT NOT NULL,            -- 属于哪张卡(问题)
  position       TEXT NOT NULL,            -- 卡内序号 p<n>(p1 / p2 …);寻址 = card_id#position
  claim          TEXT NOT NULL,            -- 答案文本(内联,不共享、不单独建表)
  -- 校验轴 = 这个 Position 的 review 顶/踩计数;credence 不存列,排序按 up/down 现算
  up_count       INTEGER NOT NULL DEFAULT 0,   -- = argument=+1 的 review 数(顶)
  down_count     INTEGER NOT NULL DEFAULT 0,   -- = argument=−1 的 review 数(踩)
  neutral_count  INTEGER NOT NULL DEFAULT 0,   -- = argument=0 的中立 review 数
  review_count   INTEGER NOT NULL DEFAULT 0,   -- 冗余:review 总数 = up+down+neutral
  -- 治理:位 / 变
  created_at     TEXT NOT NULL,
  scope          TEXT NOT NULL DEFAULT '',  -- 位:适用场景描述(自由文本软提示,非门禁)
  forked_from    TEXT,                      -- 变:Position append-only;分叉血缘(本卡内的 p<n>,只从同卡 Position 分叉)
  PRIMARY KEY (card_id, position)           -- p<n> 在卡内唯一(跟 session_marks 的 (session_id, mark) 同构)
);
-- positions 已按 (card_id, position) 主键聚簇,「列某卡的所有 Position / 取最大序号」直接走 PK 前缀,无需额外按 card_id 的索引
```

- **无 FOREIGN KEY**:SQLite 是文件罐的派生索引,容忍悬空引用(`positions.card_id`、`forked_from`(本卡内的 p<n>)都不加 FK)。这是本仓硬约束。
- `up_count` / `down_count` / `neutral_count` 就是 v3 `card_stats` 那几个计数器搬到 Position(`neutral_count` = v3 `review_neutral`);v3 的 `read_count` / `recall_count` 这套 engagement 计数 v4 **不再存**(相关性只在召回时算)。
- `cards.position_count` / `cards.link_count` / `positions.review_count` 是**冗余计数**:分别从 `positions` / `card_links` / 顶踩计数重算得到,写时维护、免 join。`position_count` 同时是「下一个 Position 序号」的来源(新答案 = `p{position_count+1}`)。
- 向量侧 embed `cards.issue`(问题级)+ `positions.claim`(答案级)两个 collection,索引在 `vectors/`(LanceDB),见 [filesystem.md](filesystem.md)。

存储分层(file canonical + SQLite index)总体模式见 [filesystem.md](filesystem.md) 与 [`../../works/v4/card.md`](../../works/v4/card.md) §8。

## 跟 v3 talk-card 的差异

| | v3 talk-card | v4 Card + Position |
|---|---|---|
| 一张卡是 | 一句 `insight` 陈述 | 一个 `issue`(问题)+ 多个 Position(答案) |
| 核心文本字段 | `card.insight` | `card.issue`(问题)+ `position.claim`(答案) |
| 顶踩计数挂在 | 整张卡(`card_stats`,6 计数) | 每个 Position(`up/down/neutral_count`) |
| 质量分 | 沉浮公式(吃 review + read + recall + age) | `credence` 现算 = f(up, down),只吃顶踩 |
| engagement | `read_count` / `recall_count` 落库 | 不存 —— 相关性召回时现算 |
| card 间关联 | `source_cards`(内联,创建即冻) | `card_links` 独立表(card↔card) |
| 出处 | `rounds[].session_id` 内联 | `card_sessions` 独立表(card↔session) |
| 翻新 | 新建 card,`source_cards` 挂 `supersedes` | 同卡内新增竞争 Position(`forked_from` 记血缘) |
| 当前胜者 | 沉浮排序算 | credence 现算最高的 Position(无 `accepted`) |
