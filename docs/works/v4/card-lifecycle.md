# card IBIS 生命周期 —— 一张卡从问题到答案到治理(v4 设计)

> **状态:设计提案,未实施。** 本篇把 v4 卡(被治理的 IBIS 问题图)的**完整生命周期**串起来:一个 session 怎么一路变成「问题 + 竞争答案 + 顶踩 + 当下结论」。核心是一条主线——**问题是客观捞出来的,答案是主观产出的**,两者的来路因此不同。
>
> 各环节的数据模型 / 字段在别处,本篇只讲**流**与**为什么这么分**:卡 / Position / credence / IBIS 边见 [card.md](card.md);写路径前端(逐 round mark)见 [session-mark.md](session-mark.md);出处两条链路见 [card-session](../../structure/v4/card-session.md) / [position-session](../../structure/v4/position-session.md)。

---

## 0. 一图看全生命周期

```
session ──逐 round 打 mark──▶ #…？ ──撞 issue 库──▶  ① 卡(问题 Issue)
   │         (以写代读)        (检索判 miss/hit)        └─ 出处:card_sessions(经 mark)
   │
   └──主观分析、形成观点──▶ 写 Position(claim) ──引用 session 作证据──▶ ② 答案(Position)
                                                  └─ 出处:position_sessions(经 indexes;mark 可选)
                                                          │
                            其它证据 顶/踩 ──▶ review(argument + 证据 indexes) ──▶ ③ credence 现算
                                                                                     │
                            卡↔卡 IBIS 边 card_links ──▶ ④ 问题图                    ▼
                                                                         召回:撞 issue → 取 credence 最高 Position → 注入
```

---

## 1. 主线:问题**客观**,答案**主观**

v4 把「一张卡」拆成**问题(Issue)** + **答案(Position)**,这俩的**来路根本不同**,别用一套机制糊:

| | 问题(Issue / 卡) | 答案(Position) |
|---|---|---|
| 怎么产生 | **客观**:认真读 session,`#…？` 把问题就地标出来,**检索**判这是不是新问题(miss=新卡) | **主观**:你**分析**一个 session、**形成一个观点**,把它写成一个候选答案 |
| 靠不靠脑补 | **不靠**——问题是 `#` 出来的、检索判新的(惊讶 grounding 在检索,不是 AI 自评) | **靠主观判断**——观点本来就是人 / agent 的主张 |
| 出处是什么 | **那条 mark**(`#…？` 在哪条感悟里冒出来)→ `card_sessions`(`mark` **必选**) | **答案从哪几轮长出来 + 引用哪些 session 作证据** → `position_sessions`(`indexes` 必选;`mark` **可选**) |
| 可不可竞争 | 一个问题就是一个问题(撞重了就是同一张卡) | **多个答案并存竞争**,靠顶/踩的 credence 现算排序 |

> **为什么两条链路 mark 颗粒度不同**:card→session **必到 mark**——卡是 `#…？` 建/连的,要支撑 `#…？` 的**双向关联**(card↔mark 互查)。position→session **mark 可选**——答案(Position)本身就是「观点」主体,主出处是它从哪几轮长出来的(`indexes`);「是哪条 mark 触发的」可顺手记(可选),但硬挂 mark 容易跟「答案这个观点本身」重复。

---

## 2. ① 问题诞生:`session → mark → #…？ → issue → 卡`(客观)

1. **session 逐 round 打 mark**(以写代读,见 [session-mark.md](session-mark.md)):一次看 2 个 round(上下文 + 当前轮),逐轮往前走、逐轮写感悟。强制真读、防走神。
2. **`#…？` 就地标问题**:感悟里冒出问题就 `#…？` 标出来(`#` 起、`？` 止)。「这条 mark 里有几个问题」是**解析出来的**,不靠 AI 自报。
3. **撞 issue 库判新旧**:每个 `#…？` embed 撞 `cards`(issue)向量库——**miss → 建新卡**(只有问题、还没答案)/ **hit → 连老卡**。判「新不新」由**检索**算(= 惊讶 grounding 在检索)。
4. **记出处**:`card_sessions(card_id, session_id, mark)` —— 这张卡是**这个 session 的这条 mark** 建/连的。**同一 card↔session 可多条**(不同 mark 各碰到它)。

产物:一张**还没答案的卡**(纯问题),挂着「它从哪条 mark 来」的出处。

## 3. ② 答案诞生:**主观分析 → 写 Position → 引 session 作证据**(主观)

1. **主观形成观点**:针对某个 issue(问题),你 / agent **分析相关 session**,得出一个**回答**——这是主观主张,不是检索捞的。
2. **写成 Position**:[`card position --card <cid> --claim '<答案>'`](../../cli/v4/card.md#card-position),`claim` 内联在 Position 上(append-only,创建即冻)。
3. **引用 session 作证据 / 来源**:`--source <session_id>:<indexes>`(可多 session)→ 落 `position_sessions(position_id, session_id, indexes, mark?)`。**这是答案的出处:它从哪几轮对话长出来的**(`indexes` 必填);**`mark` 可选**——想记「哪条 mark 触发的」就记,不强求(理由见 §1)。
4. **同一问题多答案并存**:再有不同观点 → 再加一个竞争 Position,不覆盖老的。

产物:卡从「只有问题」变成「有若干候选答案」,每个答案带着「我从哪几轮得出的」证据。

## 4. ③ 治理:顶/踩 → credence → 当下答案

1. **顶/踩(review)**:[`card review --position <pid> --argument <+1/0/-1> --cite <sid>:<idx>`](../../cli/v4/card.md#card-review)。`argument` 累成 `up/down/neutral_count`;`--cite` 的 round `indexes` 是**这次表态的证据**(append-only,错了再写一条反向)。
2. **credence 现算**:`credence = up − down`,**不落字段**,排序时算。
3. **当下答案**:召回 / 读卡时 credence 最高的 Position(平手按最近表态)——**无 `accepted` 状态位**,旧答案被踩则 credence 现算掉下去、自然不再被采,但仍在卡里可查(认知史)。

## 5. ④ 问题图:IBIS 边 + append-only

- **卡↔卡 IBIS 边**(`card_links`):`specializes` / `suggested_by` / `questions` / `replaces` / `related`——把孤立的问题连成一张**被治理的问题图**。
- **append-only 贯穿**:Position 改主意 = 加竞争 Position + 踩旧的(`forked_from_position_id` 记血缘);review 错了 = 写反向;卡不删不改。**lineage 自然成 DAG**(只能引用已存在节点)。

## 6. 三条「来路」线,各司其职(全篇关键)

| 线 | 答什么 | mark 颗粒度 | 落哪 |
|---|---|---|---|
| **启发 / 问题来源** | 这张卡是哪条 mark 的 `#…？` 建/连的 | **必选**(撑 `#…？` 双向关联) | `card_sessions(card_id, session_id, mark)` |
| **答案来源** | 这个答案从哪几轮长出来 | **可选**(主出处 `indexes`) | `position_sessions(position_id, session_id, indexes, mark?)` |
| **表态证据** | 这次顶/踩拿哪几轮当证据 | 无(`indexes`) | `reviews(position_id, session_id, indexes, argument)` |

**问题必到 mark、答案主用 indexes(mark 可选)、证据用 indexes** —— 因为问题是从认真读里**客观捞**的(指那条感悟最准、还要双向关联),答案 / 证据是**主观引用对话**(指 round 区间最准)。

## 7. 闭环:召回把图用起来

hook 阶段 [`recall`](../../cli/v4/recall.md):context → 撞 `issue`(+ `claim`)→ 命中卡 → 取 credence 最高的 Position(当下答案)→ 连 `scope` 注入。读出来的「答案」就是这整条生命周期沉淀的结论。

---

## 跟其他 works 的关系

- **[card.md](card.md)**:卡 / Position / credence / IBIS / 治理的**数据模型与设计推理**;本篇是把它们**串成时间线**。
- **[session-mark.md](session-mark.md)**:本篇 ①(问题诞生)的写路径前端细节(mark 格式、`#…？`、乐观锁)。
- **[insight-migration.md](insight-migration.md)**:老 v3 卡 → insight,跟本生命周期并行(insight 只读,不进这条写路径)。
