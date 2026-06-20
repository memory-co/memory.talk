# CardLink

**card↔card 的有向边** —— 因 `card ≡ issue`,这就是 IBIS 里 issue↔issue 那套关系(细化 / 引出 / 质疑 / 取代 / 泛关联)。卡↔卡是问题图的**关联主干**;`position` 之间不直接结网。

一条边**本身就是一个主张**(「A 是 B 的特例」「A 取代 B」也是要被证据支撑、可被顶踩的断言)。所以 v4 的 CardLink 不再是一条裸的类型边,而是**跟 Position 平行的、受治理的对象**:有自己的 `claim`(为什么这条边成立)、顶踩计数、现算 credence、证据出处(`link_sessions`)、append-only,可被 review。

> **Link 受治理,但不与 Position 合并** —— 两者**共用** review / credence / 证据 / append-only 这套机制,但**竞争语义不同**:
> - **Position = 择优(互斥竞争)**:同一卡下的 Position 互相竞争,credence 最高的(那个**没有 target 的**)就是「当下答案」。是个**选一个赢家**的关系。
> - **Link = 存在即合理(各自独立)**:每条边各自成立、互不竞争,credence = 「**这条边本身站不站得住**」。低 credence 的边 read / recall 时**淡出 / 隐藏**(过阈值),但边之间**从不竞争「哪条才是那一条」** —— 同类型多条可并存(A 同时 `specializes` B 和 C 完全合法)。
>
> 一句话:Position 的 credence 给**答案排座次**(选当下答案),Link 的 credence 给**每条边定去留**(过阈值才显示)。机制详见 [`../../works/v4/card.md`](../../works/v4/card.md) §4 的「为什么 link 也受治理但不与 position 合并对象」。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §4。card↔session 的出处关系是另一张表,见 [card-session.md](card-session.md);Position 的对照见 [card.md](card.md)。

## 寻址

一条边**从属于它的主体卡**,寻址 **`<card_id>#l<n>`**（`l` + 卡内递增序号 `l1`/`l2`…),跟 Position `<card_id>#p<n>`、mark `<session_id>#m<n>` 同构。`read card_xxx#l1`（`POST /v4/read`）读单条边;`parse_id` 认出 `card_` id 上的 `#l<n>` 分片就分派到那张卡的第 n 条边(`#p<n>` = Position,`#l<n>` = Link)。Link **没有独立前缀 id**,序号由卡自动分配。

## 形态

一条边 = **主体卡 `card_id` + 卡内序号 `link`(`l<n>`)+ 类型 `type` + 对端 `target_id` + 主张 `claim`**,非对称(不是对称的 from/to,而是「谁的边」)。

```json
{
  "card_id": "card_01jz8k2m",
  "link": "l1",
  "type": "specializes",
  "target_id": "card_01jzyyyy",
  "target_type": "card",
  "claim": "本卡是它的一个特例 —— 都走同一套 auth,只是把范围收窄到 OAuth 回调这一段。",
  "up_count": 4,
  "down_count": 0,
  "neutral_count": 1,
  "credence": 4,
  "created_at": "2026-06-18T15:00:00Z"
}
```

读「这张卡 = card_01jz8k2m 是 card_01jzyyyy 的更窄版(子问题),理由见 `claim`,这条边收到 4 顶 0 踩 → credence 高、显示」。

> `credence` 是**现算字段**（`f(up_count, down_count)`),read 响应里给出方便消费;它**不落库**(SQLite / 文件罐都没有这一列），跟 Position 的 credence 同一套算法、同一条「不落列」原则。

## 字段

### 不可变核（create 即冻,canonical 在文件罐）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | **主体卡**(谁的边);`card_<...>` |
| `link` | string | 自动 | 卡内序号 `l<n>`(`l1`/`l2`…);寻址 = `{card_id}#{link}`(如 `card_01jz8k2m#l1`)。**没有独立 `link_` id**,序号由卡自动分配 |
| `type` | string | 是 | 边类型,见 [#类型](#类型) |
| `target_id` | string | 是 | 对端 id;多为 `card_<...>`,`suggested_by` 可为一个 Position 地址 `card_<...>#p<n>` |
| `claim` | string | **是** | **这条边为什么成立**(关系断言 / 理由,如「A 是 B 的特例,因为都走同一套 auth」)。内联在边上,跟 Position 的 `claim` 同构、**create 即冻**(append-only,不可改) |
| `created_at` | string | 自动 | ISO 8601 |

### 校验轴 —— 顶踩计数（runtime,SQLite 实时维护)

跟 Position 完全同构 —— 一条边也能被顶 / 踩 / 中立(对它的 review,target = `card_id#l<n>`):

| 字段 | 类型 | 说明 |
|---|---|---|
| `up_count` | integer | 收到的 `argument=+1`（顶 / 这条边成立)review 数 |
| `down_count` | integer | 收到的 `argument=−1`（踩 / 这条边不成立)review 数 |
| `neutral_count` | integer | 收到的 `argument=0`（中立)review 数 |
| `review_count` | integer | review 总数 = `up_count` + `down_count` + `neutral_count`。**冗余缓存**,免每次求和 |

### 派生 / 自动落列

| 字段 | 类型 | 说明 |
|---|---|---|
| `target_type` | string | 对端类型:`card` / `position`,从 `target_id` 派生(带 `#p` 分片 → `position`,否则 `card`)并**单独落列** —— 「列出所有指向 Position 的边」这类查询直接按它过滤,不必解析地址 |

### 现算（不落库,read / 过滤时算）

| 量 | 怎么算 | 说明 |
|---|---|---|
| `credence` | `f(up_count, down_count)` | 这条边**自己**的校验分(`up−down` / Wilson),跟 Position credence 同一函数。**不落列**,read 时算 |
| 「显不显示」 | read / recall 时 credence 过阈值才带出 | **存在即合理**:低 credence 的边淡出 / 隐藏,但**不与同类型其它边竞争**;没有「胜出的那一条」 |

## 类型

| `type` | 含义 | 方向 |
|---|---|---|
| `specializes` | A 是 B 的更窄版(子问题,**DAG 非树**) | 有向 |
| `suggested_by` | A 被某节点引出来(出处 / 因果);**对端可为 Position**(答案也能勾出新问题) | 有向 |
| `questions` | A 质疑 B 的前提 / 框架 | 有向 |
| `replaces` | A 重述并取代 B(**保留历史**,不删 B) | 有向 |
| `related` | 兜底泛关联 | 无向 |

> IBIS 关系集**不完备**,可按需补 `depends_on` / `part_of`。未识别 `type` 报 400。
>
> **`replaces`(issue 层)≠ `forked_from`(position 层)**:`replaces` 是一个**问题**重述取代另一个问题;`forked_from` 是同一问题下一个**答案**分叉自另一个答案。两个不同机制,别混。

## 多值 / 方向

- **五类型全多值,且各自独立成立(存在即合理)**:同一 `(card_id, type)` 下可多条(如 `specializes` 多父、A 同时特化 B 和 C → 统一边表、不内联成列)。每条边的去留只看**它自己的** credence,不与同类型其它边竞争。
- **不重边**:UNIQUE `(card_id, type, target_id)` —— 同一主体、同类型、同对端只一条边(改主意是**踩它 / 加反向 `replaces` 边**,不是再建一条同边)。`link`(`l<n>`)是这条边的卡内地址,跟 PK 一起唯一。
- **`related` 无向**:写时规范化排序(两端按 id 排好)只存一遍,避免 A→B、B→A 双份。

## 证据 / 出处 —— link_sessions

跟 Position 的 [`position_sessions`](position-session.md) 同构:一条边**在哪几轮对话里被观察 / grounding 到**,落 `link_sessions`,支持多 session(`card link … --source <sid>:<idx>` 可重复)。

```json
{
  "card_id": "card_01jz8k2m",
  "link": "l1",
  "session_id": "sess_def456",
  "indexes": "30-34",
  "created_at": "2026-06-18T15:00:00Z"
}
```

读「边 `card_01jz8k2m#l1`(本卡 specializes card_yyyy)是从 `sess_def456` 的第 30–34 轮观察出来的」。

```sql
-- link → session 出处(这条边从哪几轮观察 / grounding 出来);支持多 session
CREATE TABLE link_sessions (
  card_id     TEXT NOT NULL,             -- 边的主体卡
  link        TEXT NOT NULL,             -- 哪条边(卡内序号 l<n>;寻址 card_id#link)
  session_id  TEXT NOT NULL,             -- 哪个 session(扁平,可 join;无 FK)
  indexes     TEXT NOT NULL,             -- 这条边来自的 round 区间(语法同 reviews.indexes:30-34 / 3,7,12)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, link, session_id)
);
CREATE INDEX idx_link_sessions_session ON link_sessions(session_id);  -- 反查「这个 session 观察出了哪些边」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。每个 `--source` 给不同 session → 多条。
- 对照三条出处线:`card_sessions`(card→session,经 mark)/ `position_sessions`(position→session,经 indexes)/ `link_sessions`(link→session,经 indexes)。

## 存储

```sql
-- 主体卡的有向边(= IBIS issue↔issue,因 card≡issue);受治理对象,平行于 positions
CREATE TABLE card_links (
  card_id     TEXT NOT NULL,              -- 主体卡(谁的边),不是对称 from/to
  link        TEXT NOT NULL,              -- 卡内序号 l<n>(l1 / l2 …);寻址 = card_id#link(#l<n> 分片)
  type        TEXT NOT NULL,              -- specializes|suggested_by|questions|replaces|related
  target_id   TEXT NOT NULL,              -- 对端 id:多为 card_…;suggested_by 可为 card_…#p<n>(一个 Position)
  target_type TEXT NOT NULL,              -- 'card' | 'position',从 target_id 派生(带 #p 分片 → position)
  claim       TEXT NOT NULL,              -- 这条边为什么成立(关系断言,内联、create 即冻 append-only)
  -- 校验轴 = 这条边的 review 顶/踩计数;credence 不存列,过滤/排序按 up/down 现算
  up_count      INTEGER NOT NULL DEFAULT 0,   -- = argument=+1 的 review 数(顶:这条边成立)
  down_count    INTEGER NOT NULL DEFAULT 0,   -- = argument=−1 的 review 数(踩:这条边不成立)
  neutral_count INTEGER NOT NULL DEFAULT 0,   -- = argument=0 的中立 review 数
  review_count  INTEGER NOT NULL DEFAULT 0,   -- 冗余:review 总数 = up+down+neutral
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, link),               -- l<n> 在卡内唯一(跟 positions 的 (card_id, position) 同构)
  UNIQUE (card_id, type, target_id)          -- 不重边:同一(主体, 类型, 对端)只一条;related 无向 → 写时规范化排序
);
CREATE INDEX idx_card_links_target ON card_links(target_id);  -- 反查入边「指向某卡 / 某 Position 的边」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。canonical 是文件罐 `cards/<bucket>/<card_id>/links/l<n>.json`(`type` + `target_id` + `claim` + `created_at`),跟 `positions/p<n>.json` 同构;`card_links` 表是其派生索引 + 顶踩运行态。
- **PK `(card_id, link)`**:跟 `positions` 一样按主体卡聚簇,「列某卡的所有边 / 取最大序号」直接走 PK 前缀。`link` = `l<n>`,是这条边的卡内地址。
- **UNIQUE `(card_id, type, target_id)`**:保证不重边;`target_type`(`card` / `position`)从 `target_id` 派生、单独落列,便于按对端类型过滤,免每次解析地址。
- `up_count` / `down_count` / `neutral_count` / `review_count` 跟 Position 同构;`credence` 不落列,read / 过滤时按 `up` / `down` 现算。**append-only**:边写错了不删不改,**踩它**(credence 现算掉下去 → 隐藏)或**加一条反向 `replaces` / 反例边**。

## 文件罐

```
cards/<bucket>/<card_id>/
├── card.json
├── positions/p<n>.json
└── links/
    ├── l1.json                  # canonical:type + target_id + claim + created_at(边核不可变),文件名 = l<n>
    └── l2.json
```

跟 `positions/p<n>.json` 同构:边的不可变核(`type` + `target_id` + `claim` + `created_at`)落文件罐;顶踩计数 / `target_type` 派生 / review 在 SQLite。

## 反查

「指向某卡 / 某 Position 的边」(入边)走 `idx_card_links_target`(`target_id`);本表 PK 已覆盖「某主体卡的出边」。`read <card_id>` 同时返回 out / in 两向(各带 `claim` + 现算 credence)。

## 可 review

一条边跟 Position 一样可被表态(target = `card_id#l<n>`):`POST /v4/cards/{cid}/links/{l}/reviews`(CLI `card review --target card_xxx#l<n>`)。Review 的 target 已从「只 Position」泛化为「**Position 或 Link**」,带一个从 `#p`/`#l` 分片派生的 `target_kind`(position | link),见 [review.md](review.md)。`argument=+1`/`−1`/`0` 累成边的 `up`/`down`/`neutral_count`,credence 现算决定这条边显不显示。

## 跟 v3 source_cards 的差异

| | v3 `source_cards` | v4 `card_links` |
|---|---|---|
| 载体 | card 的内联字段(创建即冻) | 独立**受治理对象**(可后续增边,有 `claim` / 顶踩 / credence / review / 证据) |
| 关系 | `derives_from` / `supersedes` 两种 | 五类型(IBIS) |
| 对端 | 只 card | card 为主,`suggested_by` 可指 Position(`card_…#p<n>`) |
| 方向 | 单向(本卡 → 源卡) | 有向为主,`related` 无向 |
| 可治理 | 否(裸字段) | **是**:`claim` + review(`card_id#l<n>`)+ 现算 credence + `link_sessions` 证据,append-only |
| 寻址 | 无(内联) | `card_id#l<n>`(卡的附属,可 `read`) |
