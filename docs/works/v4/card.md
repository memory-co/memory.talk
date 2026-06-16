# card — 被治理的问题图(v4 设计)

> **状态:设计提案,未实施。** 这是 **v4 的 card**:一张卡不再是「一句陈述」,而是「**一个问题 + 它的若干答案(竞争中的候选)**」,所有卡连成一张**被治理的问题图**。
>
> **它不改 v3 的卡,而是另起一代。** v3 现有的那套卡(`insight` 字段 + 论坛动力学 stats)**整体改名成 `insight`、数据保留、后续慢慢下掉**——把 `card` 这个名字腾出来给本设计。三者关系见 [§0](#0-三个名字v3-card--insight--v4-card)、迁移见 [§9](#9-与-v3--insight-的共存与迁移)。
>
> 本稿走的是「从最朴素的 card 出发、被一个个具体问题推着长成什么形状」的叙事:IBIS、易经四维这些名字,都是走到那一步才出现。

相关:
- v3 论坛动力学(沉浮 + 三轴 stats,**即将改名 insight 的那套**): [../v3/forum-dynamics.md](../v3/forum-dynamics.md)
- v3 卡数据结构(`insight` 字段 + rounds + source_cards): [../../structure/v3/talk-card.md](../../structure/v3/talk-card.md)
- v3 卡创建流程(rounds 展开 + DAG,本稿 §6 写路径取代它): [../v3/card-creation-flow.md](../v3/card-creation-flow.md)
- explore 先验/后验抽卡工作区(抽卡的上游工作台,产物从 insight 卡换成 v4 卡): [../v3/explore.md](../v3/explore.md)
- file-canonical 模式(file 罐 + SQLite 瘦索引,本稿沿用): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)
- migration 模块(schema 版本化演化,v4 落地要新版迁移): [../v3/migration.md](../v3/migration.md)

---

## 0. 三个名字:v3 card / insight / v4 card

| | 它是什么 | 这次的命运 |
|---|---|---|
| **v3 card** | 现在线上的卡:一句 `insight` + rounds + source_cards,沉浮靠 review/read/recall 三轴 | **改名 `insight`**,数据保留、只读可搜,不再是抽卡主路径 |
| **insight** | 上一行改名后的产物,**就是 v3 card** | 慢慢下掉(后续可逐条投影进 v4 图,见 §9) |
| **v4 card** | 本稿:一张卡 = **一个 Issue(问题)+ 若干 Position(答案候选)**;哪个答案胜出靠 review 顶/踩 + 沉浮竞争;卡连成被治理的问题图 | 新建,**复用腾出来的 `card_` 前缀 + `card` 命令** |

> 一句话:**v4 把"陈述卡"升级成"问答卡 + 问题图 + 治理层"。** v3 的卡没死,只是退到 `insight` 这个名字下慢慢退场。

---

## 1. 起点:最朴素的 card 会撞的四堵墙

最朴素的做法,也正是 v3 在做的:`session → 抽一句 insight → 存起来 → 检索时注入 context`。

它会连撞四堵墙——本稿四次「推」各自就是在拆这四堵:

| # | 墙 | v3 的痛点 | 哪一推拆它 |
|---|---|---|---|
| 1 | **卡是孤立陈述** | 难索引、难关联,还互相矛盾:「用户喜欢简洁」vs「用户有时要详细」谁说了算? | [§2 问答化](#2-第一推card--一个问题--它的若干答案) + [§4 IBIS](#4-第三推问题连成图--这套东西叫-ibis) |
| 2 | **「对不对」和「现在相不相关」搅在一起** | 一张卡被频繁 recall ≠ 它被验证过;`review_count` 和 `recall_count` 混在一个沉浮公式里 | [§3 两根正交轴](#3-第二推credence--salience校验轴和显著轴是两回事) |
| 3 | **凭什么信一个答案** | 从一句话抽出的断言,可能只是模型臆测,没有证据链 | [§3 credence ← review 证据](#3-第二推credence--salience校验轴和显著轴是两回事) |
| 4 | **卡会过期、会被场景误用** | 去年的「住杭州」、投资立场卡跑去给育儿建议;v3 只有 `age_days` 一个弱信号 | [§5 治理四维](#5-第四推给卡装上治理--时位势变) |

---

## 2. 第一推:card = 一个问题 + 它的若干答案

针对墙 1。与其存陈述「用户喜欢简洁」,不如存「**用户偏好什么回答风格?**」这个**问题**,底下挂上**若干候选答案**——卡变成「**一个问题 + 它的多个答案**」。

为什么这步对:

- **问题是天然的索引**:一个问题就是它那些答案的*适用条件*。检索时拿当前 context 去**撞问题**(而非撞陈述),命中率和精度都更高。
- **一个问题可以有多个答案在竞争**:哪个答案更好,**不靠创建时拍板**,而是后面用 review 顶/踩 + 沉浮**竞争**出来(§3)。
- **同一答案能挂多个问题**:所以答案**内容**要**单独存、去重、不复制**(去重机制见 [§12](#12-诚实边界--待定) 待定)。
- **没答的问题本身有价值**:一张还没有 `accepted` 答案的卡 = 一个**开放回路**(`open = 1`),在等证据。

于是一张 v4 卡 = **一个 Issue + 若干 Position**,涉及三种对象 + 一种复用 v3 的信号:

| 对象 | 是什么 | 角色 |
|---|---|---|
| **Card ≡ Issue** | 卡的那个**问题**(一张卡 = 一个问题,1:1) | **检索单元 + 图节点**(embed 问题;卡↔卡连边见 §4) |
| **Position** | 卡底下的**一个候选答案**(引一个 Claim) | **被顶/踩、被沉浮排序的那个东西**——治理 + credence 都挂它身上 |
| **Claim** | 去重后的答案**内容本身** | 内容载体(可被多个 Position / 多张卡共享) |
| **Review**(复用 v3) | 带 session 证据(`indexes`)的一次**顶/踩**(`score` ±1/0),**target = Position** | 既是「证据」也是「投票」(§3) |

> **别再把 Position 当成整张卡**(这是上一稿的错):**card = 一个 Issue + 若干 Position**。Position 是**答案候选**,卡是**问题 + 这些候选的集合**。「哪个 Position 是这张卡的答案」不是写死的,是 review + 沉浮**浮**出来的(`accepted` ≈ Stack Overflow 的采纳答案)。
>
> **没有独立的 Argument 对象**:支持/反对一个 Position 的「证据」就是**带 session 证据的 review**——v3 的 review 本来就带 `indexes`(证据)+ `score`(顶/踩),它**就是**那条「证据 + 表态」。所以 Argument 直接并进 Review,不另起对象。
>
> **跨问题关联走「共享 claim」**:两张卡(两个问题)引同一个 Claim,天然就关联;Position 之间**不直接结网**(图的骨架在卡/问题层,§4)。

---

## 3. 第二推:credence ⊥ salience(校验轴和显著轴是两回事)

针对墙 2、墙 3。给每个 **Position**(答案候选)**两根正交的轴**,分两个字段存,**绝不搅在一起**:

| 轴 | 字段 | 问的是 | 谁来推它 | 被什么往下压 |
|---|---|---|---|---|
| **校验轴** | `credence`(← `corroborations` / `contradictions`) | 这个答案**对不对**、验过没 | **对这个 Position 的 review 顶/踩**(带 session 证据) | **只有真·反驳**(踩 / contradiction) |
| **显著轴** | `salience` / `momentum` | 这个答案现在**相不相关** | recall / read(被路过、被看) | **沉默**(主题没再出现) |

**关键:论坛动力学没变,只是从「整张卡」下放到「Position」。** v3 的 review/read/recall + 沉浮那套**原封不动**,只把 target 从 `card_id` 换成 `position_id`:

- `corroborations` / `contradictions` **就是这个 Position 的 `review_up` / `review_down`**(顶 / 踩)。`credence` 是它俩的函数(顶抬、踩压、沉默不动)。
- `momentum` 还是那条沉浮公式,只是现在**在一张卡内部给若干 Position 排序**——把最该信、最相关的答案浮上来,`accepted` = 浮上来的那个。
- 所以「**哪个 Position 更好**」= 用**原有的 session 证据投票机制(review)**对 Position 顶/踩,再让沉浮排序——**不是新发明的机制**。

最容易写错、也最关键的一点:**沉默 ≠ 确认**。后续对话**绝大多数**对一个 Position 是沉默的(主题压根没再出现):

- 沉默只让它**沉底**(动 `salience`/`momentum`),**不动它的对错**(`credence` 不变)。
- 校验**只认**真·顶 / 真·踩(带证据的 review),无关的不算(§6 写路径靠「检索匹配」判定相不相关)。

> **对照 v3**:v3 的 review/read/recall 挂在**整张卡**上——一张卡只有一个「立场」,赞踩都算到这一张。v4 把它**下放到 Position**:同一个问题下的**不同答案各自被顶踩、各自沉浮**,于是「这个问题到底哪个答案对」第一次有了**结构**(竞争 + 采纳),而不是糊在一张卡上。

---

## 4. 第三推:问题连成图 —— 这套东西叫 IBIS

针对墙 1 的后半(关联)。卡已经是「问题 + 多个答案 + 证据」,问题与问题之间显然还互相关联:一个问题是另一个的细化、一个答案会引出新问题……

把这些关联显式化之后会发现:**被 card 的问题独立推出来的东西,学术上早有名字——IBIS(Issue-Based Information System)**。它的节点 Issue / Position 正好对上(它的 Argument 在本设计**并进 Review**,见 §2),问题之间的关系也正好是它那套。直接借本体,不重造轮子。

**什么连什么**:**卡 ↔ 卡**(= `issue ↔ issue`,因 card ≡ issue)是**关联主干**;`position` 之间不直接结网;跨卡的关联还可靠「两张卡共享同一个 claim」间接成立。

| 边 type | 含义 | 方向 |
|---|---|---|
| `specializes` | A 是 B 的更窄版(子问题,**DAG 非树**) | 有向 |
| `suggested_by` | A 被某节点引出来(出处 / 因果) | 有向 |
| `questions` | A 质疑 B 的前提 / 框架 | 有向 |
| `replaces` | A 重述并取代 B(**保留历史**,不删 B) | 有向 |
| `related` | 兜底泛关联 | 无向 |

> IBIS 关系集**不完备**,可按需补 `depends_on` / `part_of`。存储上是**两套抄**:**本体抄 IBIS**(节点 + 边的类型学),**投票 / 采纳 / 去重那套机制抄 Stack Overflow**(**review 顶/踩 → credence**;`accepted` 采纳 = 浮上来的那个答案;Claim 去重 = 答案合并)。这些 issue↔issue 的边,落地就是**卡↔卡**的边(`card_links`,§8)。

---

## 5. 第四推:给卡装上治理 —— 时 / 位 / 势 / 变

针对墙 4。IBIS 给了**结构**,但没说一张卡**何时过期、在哪能用、排多前、怎么变迁**。把这层显式建出来,正好对上四个工程维度——助记叫「时位势变」(去魅:就是 *时间有效性 / 适用域 / 排序 / 生命周期*,「易经」只是助记标签):

| 维度 | 字段 | 干什么 | 防的失败 |
|---|---|---|---|
| **时** time | `TimeScope`:`confirmed_at` / `expires_at` / `review_at` / `half_life_days`(创建时间用 Position 顶层 `created_at`,不重复存) | 时间有效性 + 重验节奏 + 半衰 | 过期假设支配当下 |
| **位** scope | `Scope`:`domain × role × authority × layer` + `exclusions` | 适用域门禁 | 跨场景误用(投资卡去答育儿) |
| **势** momentum | 真讨论(扣除仅浏览)− shadow risk 的排序量 | 排序 | 高频低验证的卡支配回答 |
| **变** change | 状态机:`active` / `forked` / `dormant` / `archived`(+ `superseded_by` / `forked_from`) | 生命周期 | 静默覆盖、认知史丢失 |

三个**最容易错**的要点:

1. **staleness(时间衰减)≠ wrongness(被反驳)**。一张卡可以没被反驳、`credence` 还高,但**已过期**,照样不该用。「不该用」有**两个独立来源**——**过期(时)** 和 **位错(位)**——都跟「对不对(credence)」无关。
2. **易经的「位」≠ IBIS 的 Position 节点**。这里的「位」是**适用域门禁**,本稿叫它 **Scope**;它和「Position(卡底下的答案候选)」是两回事,**别混**。
3. **真正比 IBIS 多出来的增量只有两处**:**Scope/适用域 + exclusions**,和 **fork**(信念分叉时**分支而非覆盖**,保住认知史)。其余三维大半是给已有概念起名(时↔staleness、**势↔v3 的 `recall_count`+`read_count`**、变↔lifecycle)。

**两条路径,别混**:

- 检索时,一张卡要连过**三道防火墙**(**时 → 位 → 势**)才允许塑造回答(§7 读路径)。
- **变** 是**离线**的生命周期状态机,**不在召回热路径**上。其中 **resurrect = dormant→active 的转移**(不是常驻状态,所以状态枚举只有 `active` / `forked` / `dormant` / `archived` 四个);一张 Position 被**取代**时转 `archived` 并置 `superseded_by`。注意 **issue 层的 `replaces` 边**(一个问题重述取代另一个问题)和 **position 层的 `superseded_by`**(同一问题下一个答案取代另一个答案)是两个不同机制,别混。

`Scope` 的 JSON 形:

```json
{
  "domain": ["billing", "infra"],
  "role": ["backend-dev"],
  "authority": "preference",     // fact | preference | policy | ...
  "layer": "project",            // global | project | session
  "exclusions": ["parenting", "investment-advice"]
}
```

---

## 6. 写路径:每轮对话怎么变成卡 —— 旁白 → 惊讶 → question

前面讲卡长什么样、怎么用;这节讲卡**怎么从对话里长出来**。这步本身也是演进出来的:

| 版本 | 做法 | 为什么换掉 |
|---|---|---|
| **v0** | 给**每个** round 加一条**旁白**(标「为什么有这段对话」+ 提几个问题) | 绝大多数 round 平淡,每条都标只产生噪声 |
| **v1** | 只标「**惊讶**」旁白(普通旁白无意义) | 问题转成:怎么判一轮惊不惊讶 |
| **v2** | 惊讶用 **logprob** 测(带 / 不带用户模型两遍打分,`ℓ_model − ℓ_base`) | Opus 接口给不了 logprob,得挂本地打分器,重 |
| **v3(当前选定)** | 一条旁白**只要能冒出 question,就近似一个惊讶**——把「检测惊讶」和「产出 question」合成一步,免掉 logprob | —— |

**命门**(否则退化成 confabulation):惊讶**不是**「生成了 question」(LLM 永远能生成 question),而是「**生成的 question 在图里找不到已被自信回答的对应**」。所以拿生成的 question 去 **issue 向量库检索匹配**,按结果分三岔:

| 检索结果 | 判定 | 动作 |
|---|---|---|
| **miss**(最近邻距离 > θ) | 真·新问题 | 建**新卡**(新问题),起 why→Q→A 的第一个 Position,`birth_surprise` = 距离 |
| **hit** 某卡、且它 `accepted` 的答案一致 | 不惊讶 | 对那个 Position **顶一票**(review +1 → `corroborations++`,轻推 credence) |
| **hit** 某卡、但与它现有答案**冲突** | **矛盾(最高价值)** | 给旧 Position **踩一票**(review −1)+ 在**同一张卡下新建一个竞争 Position** |

**惊讶幅度**(排序 / 预算用)用**检索距离**(question 到图里最近节点的 cosine)当代理,**也不用 logprob**。logprob 降为可选高保真层,大概率用不上。

> 写路径的上游工作台是 **explore**(先验/后验抽卡工作区,[../v3/explore.md](../v3/explore.md)):在先验 session 上跑这条「旁白→惊讶→question」抽出 v4 卡,用后验 session 回流证据(§7)。explore 的产物从「insight 卡」换成「v4 卡(问题 + 答案)」,工作台机制不变。
>
> **这条写路径落地成什么 ergonomics** —— 逐 round 标注(以写代读)+ 标注里 `#问题` 自动建卡 / 关联 —— 见 [session-annotation.md](session-annotation.md)。那篇是本节逻辑的**具体前端**:annotation = 旁白,`#问题` = question,新卡/关联复用本节三岔。

---

## 7. 读路径 + DTO

### DTO:Card + Position

一张卡 = 一个 **Card**(问题)+ 若干 **Position**(答案);治理四维挂在 **Position** 上,Card 只管问题 + 连边:

```python
class Card(BaseModel):                      # = 一个问题(≡ Issue),图节点
    card_id: ID                             # card_<ulid>
    question: str                           # 检索锚点(embed 它)
    open: bool = True                       # 还没 accepted 答案 = 开放回路
    created_at: str
    # 卡↔卡的边(§4)单独存 card_links,不内联

class Position(BaseModel):                  # 卡底下的一个答案候选;被顶踩、被沉浮的就是它
    position_id: ID; card_id: ID; claim_id: ID    # 属于哪张卡、引哪个 Claim(答案内容)
    # 校验轴(§3)= 这个 Position 的 review 顶/踩
    credence: float = 0.5
    corroborations: int = 0                 # = review_up(顶)
    contradictions: int = 0                 # = review_down(踩)
    accepted: bool = False                  # 沉浮浮上来的那个 = 本卡当前答案
    cited_rounds: list[RoundRef] = []       # [{session_id, index}] 抽这个答案的出处
    # 治理:时 / 位 / 势 / 变(§5)
    time: TimeScope                         # confirmed_at/expires_at/review_at/half_life_days
    scope: Scope                            # domain×role×authority×layer + exclusions
    momentum: float = 0.0                   # 真讨论(扣除仅浏览)− shadow risk;在卡内给 Position 排序
    change_state: Literal["active","forked","dormant","archived"] = "active"
    superseded_by: ID | None = None
    forked_from: ID | None = None           # 变:分支保留认知史
    birth_surprise: float | None = None     # §6 的检索距离
    created_at: str
```

`Claim`(`claim_id` + `content`,去重共享)、`Review`(`target = position_id` + `indexes` + `score`,**复用 v3**)、`CardLink`(卡↔卡边)各自是独立 BaseModel。**治理只挂 Position;Card 只管问题 + 连边;证据/投票是 Review。**

### 读路径

```
召回   : context → embed → 撞卡的问题(向量 + FTS)→ 取命中卡底下的 Position
三防火墙(逐个 Position 过,顺序即 时 → 位 → 势):
  时   : 过 expires_at? 过了 review_at? half_life_days 衰减后还剩多少? → 不合格挡掉
  位   : context 的 domain/role/authority/layer 不在 scope 内,或命中 exclusions → 挡掉
  势   : 幸存 Position 按 momentum 排序;一张卡通常只取浮在最上面的那个(accepted)
注入   : 幸存者按 momentum 进 context
回流   : 用户在后续 round 顶/踩 → 一条 review(带证据)→ 动那个 Position 的 credence/沉浮(= §6 写路径)
```

> **结构**(卡=问题+答案候选)决定能不能连、怎么连;**治理**决定何时有效、何处可用、排多前、怎么变;**review + 沉浮**决定一张卡里哪个答案胜出;**写路径**决定它们怎么从对话长出来。

---

## 8. 存储:file-canonical 罐 + SQLite 瘦索引 + searchbase

沿用本仓 [file-canonical 模式](../v3/file-canonical-pattern.md):**文件罐是 canonical**(可移植 / 审计);**SQLite 是派生索引**(既照抄不可变字段供查询,也存可变运行态——跟 v3 `cards`/`card_stats` 一个路子);检索进 searchbase。

**不可变核 vs 可变运行态**:

- **不可变核**(create 即冻,canonical 在文件罐):Card 的 `question`、Position 的 `(card_id, claim_id, cited_rounds, birth_surprise, created_at)`、Claim 的 `content`。
- **可变运行态**(SQLite 实时维护):`credence / corroborations / contradictions / accepted`、整个治理四维、卡的 `open`、`card_links`。SQLite 同时**照抄一份不可变字段**供查询,崩了能从文件罐重建。

```
cards/<bucket>/<card_id>/card.json            ← canonical:question + created_at(问题不可变)
cards/<bucket>/<card_id>/positions/<pid>.json ← canonical:claim_id + cited_rounds + birth_surprise(答案核不可变)
claims/<bucket>/<claim_id>/claim.json         ← canonical:content(去重共享)
                                                credence/治理/沉浮/边/review = SQLite 派生运行态
```

> Position 的**文件**放在它所属卡的目录下(`cards/<card_id>/positions/`)——一张卡 = 一个问题 + 它的答案们,物理上聚在一起。**review 不进文件罐**(沿用 v3:review 有自己的 canonical),只在 SQLite 里 target 到 `position_id`。

**SQLite 派生索引 + 运行态**(v4 卡表是再后面一版迁移,见 §9):

```sql
CREATE TABLE cards (                       -- = 一个问题(≡ Issue),图节点
  card_id    TEXT PRIMARY KEY,             -- card_<ulid>(v4 复用 card_ 前缀;v3 已腾给 insight_)
  question   TEXT NOT NULL,                -- 检索锚点(进向量库)
  open       INTEGER NOT NULL DEFAULT 1,   -- 还没 accepted 答案 = 开放回路
  created_at TEXT NOT NULL
);
CREATE TABLE claims (                      -- 去重共享的答案内容
  claim_id   TEXT PRIMARY KEY,             -- claim_<ulid>
  content    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE positions (                   -- 卡底下的答案候选;被顶踩 + 沉浮的就是它
  position_id    TEXT PRIMARY KEY,         -- pos_<ulid>
  card_id        TEXT NOT NULL,            -- 属于哪张卡(问题)
  claim_id       TEXT NOT NULL,            -- 答案内容
  cited_rounds   TEXT NOT NULL DEFAULT '[]',  -- 派生副本;canonical 在 positions/<pid>.json
  -- 校验轴 = 这个 Position 的 review 顶/踩(§3)
  credence       REAL    NOT NULL DEFAULT 0.5,
  corroborations INTEGER NOT NULL DEFAULT 0,   -- = review_up(顶)
  contradictions INTEGER NOT NULL DEFAULT 0,   -- = review_down(踩)
  review_neutral INTEGER NOT NULL DEFAULT 0,
  read_count     INTEGER NOT NULL DEFAULT 0,   -- 显著轴(recall_count 同 v3 改派生,不存列)
  accepted       INTEGER NOT NULL DEFAULT 0,
  -- 治理:时 / 位 / 势 / 变(§5)
  created_at     TEXT NOT NULL,
  confirmed_at   TEXT, expires_at TEXT, review_at TEXT, half_life_days REAL,
  scope          TEXT NOT NULL DEFAULT '{}',  -- 位:Scope JSON
  momentum       REAL NOT NULL DEFAULT 0.0,
  change_state   TEXT NOT NULL DEFAULT 'active',  -- active|forked|dormant|archived
  superseded_by  TEXT, forked_from TEXT, birth_surprise REAL,
  FOREIGN KEY (card_id)  REFERENCES cards(card_id),
  FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);
CREATE INDEX idx_pos_card  ON positions(card_id);
CREATE INDEX idx_pos_claim ON positions(claim_id);
-- review:复用 v3 review 形状(indexes 证据 + score 顶/踩),只把 target 从 card_id 换成 position_id
CREATE TABLE reviews (
  review_id   TEXT PRIMARY KEY,            -- review_<ulid>
  position_id TEXT NOT NULL,               -- 顶/踩哪个答案(v3 这里是 card_id)
  session_id  TEXT NOT NULL,
  indexes     TEXT NOT NULL,               -- session 证据(哪几个 round)
  score       INTEGER NOT NULL,            -- +1 顶 / −1 踩 / 0 中立
  comment     TEXT,
  created_at  TEXT NOT NULL,
  FOREIGN KEY (position_id) REFERENCES positions(position_id)
);
CREATE INDEX idx_reviews_position ON reviews(position_id, created_at DESC);
CREATE TABLE card_links (                  -- 卡↔卡的边(= IBIS issue↔issue,因 card≡issue)
  from_card  TEXT NOT NULL, to_card TEXT NOT NULL,
  type       TEXT NOT NULL,               -- specializes|suggested_by|questions|replaces|related
  created_at TEXT NOT NULL,
  PRIMARY KEY (from_card, to_card, type)
);
```

> `corroborations` / `contradictions` / `review_neutral` / `read_count` 就是 v3 `card_stats` 那几个计数器**搬到 Position**;`credence` 由顶/踩派生,`momentum` 由沉浮公式派生。**没有 `arguments` 表**——证据就是 `reviews`。

**searchbase**(复用 [searchbase 端口](../v3/searchbase-extraction.md),零侵入):

| collection | embed 什么 | 用途 |
|---|---|---|
| `cards` | `question` | **检索主单元**(读路径撞问题、写路径 §6 匹配 question 都打它;v3 `cards` collection 已在 §9 改名腾出此名) |
| `claims` | `content` | 答案去重(**仅当 [§12](#12-诚实边界--待定) 选 embed 去重时才需要**;归一化文本精确去重则无此 collection) |
| `insights` | `insight`(= v3 `cards` collection 原样 copy,**flat 布局、fields schema 为空**) | insight 仍可搜,见 §9 |

---

## 9. 与 v3 / insight 的共存与迁移

目标:**腾出 `card` 这个名字**给 v4,同时**一行用户数据都不丢**。分三步,前两步是这次就要做的「改名 + 保数据」,第三步是「慢慢下掉」的后话。

### 步骤一:v3 card → insight(改名,保数据)

把现有那套卡整体改名 `insight`,落成**迁移框架里的下一版**(首启动 catch-up 原地升级):

> **别把迁移 `vN` 当产品代号**:迁移框架的版本号跟这篇说的「v3 / v4」是**两套独立编号**。当前 schema 在迁移 **`v2`**(本会话刚加的 explore),所以**改名是迁移 `v3`**(`migrations/v3/{init,up}_{database,searchbase}.py`);**v4 新卡表是再后面一版迁移**(`v4` 或更后)。下表的「v3 / 改名后」指**产品语义**,不是迁移版本号。

| 层 | v3(card) | → 改名后(insight) |
|---|---|---|
| CLI | `memory.talk card` | `memory.talk insight` |
| API | `/v3/cards` | `/v3/insights` |
| SQLite 表 | `cards` / `card_stats` / `card_source_cards` | `insights` / `insight_stats` / `insight_source_cards` |
| LanceDB collection | `cards` | `insights` |
| id 前缀 | `card_<ulid>` | `insight_<ulid>`(连带重写 `reviews` / `recall_event` / `source_cards` 里的引用) |
| 文件罐 | `cards/<bucket>/...` | `insights/<bucket>/...` |
| 代码符号 | `service/cards.py` 等 | `service/insights.py` 等 |

> **searchbase 侧不是「改名」是「拷贝」**:`AdminBackend` **没有** `rename_collection`(只有 create / drop / copy_rows / add·rename·drop_column,见 [migration.md](../v3/migration.md))。所以 LanceDB 的 `cards`→`insights` 走 `create_collection('insights')` + `copy_rows(cards→insights)` + `drop_collection('cards')`(在 `migrations/v3/up_searchbase.py`)。`cards` collection 是 flat 布局、只 embed `insight`(fields schema 空),原样搬即可;或干脆用 [index-backfill](../v3/index-backfill.md) 从文件罐重灌。
>
> **id 前缀重写是最重的一段**:`card_<ulid>`→`insight_<ulid>` 要一致改写**所有**跨对象引用——`reviews.card_id`、`card_source_cards.{card_id, source_card_id}`、`recall_event.{returned_ids, skipped_ids}`(JSON 数组)、`search_log.response_json`,以及文件罐 `cards/<bucket>/` 的 bucket(= `card_id[5:7]`,前缀变了 bucket 跟着变)。**若想降风险可分两段**:先改名 CLI/API/代码/SQLite 表/collection,**`card_` id 前缀暂留**,把 id 重写单独作为后续一次迁移(属于「慢慢下掉」的一部分)。本稿倾向一次到位,把这个开关留给实施时定。

### 步骤二:v4 card 全新起(复用腾出来的名字)

insight 让出 `card` / `card_` 之后,v4 在干净地基上建:`cards`(问题)/ `positions`(答案,`pos_`)/ `claims` / `reviews`(target=position)/ `card_links`,**卡复用 `card_` 前缀 + `card` 命令**。**v4 与 insight 物理隔离**(不同表、不同 collection、不同前缀),互不干扰地共存。

### 步骤三:慢慢下掉 insight(后话,本稿不强求)

- insight **只读可搜**:老数据继续能 `search` / `read` / 回看,但**新抽卡只写 v4**。
- 可选**投影**:把每条 insight **投影**进 v4 图——一条 insight →(一张**卡** =「这条洞见在答的问题」+ 一个 **Position** = 洞见本身那个答案,其 `rounds`→`cited_rounds`;老 review 跟着 target 到这个 Position)。投影完的 insight 可 `archived`。
- 投影是渐进、可暂停的;投影策略 / 触发时机另案。

---

## 10. API / CLI 面

- **端点**(复数):`/v4/cards`(问题 + 它的 Positions)、`/v4/cards/{id}/positions`、`/v4/positions/{pid}/reviews`(顶/踩)、`/v4/claims`、`/v4/card-links`。读路径 `/v4/recall` 走「撞问题 → 取 Position → 三防火墙 → momentum 排序」。
- **CLI**:`memory.talk card`(v4 复用此命令),语义 = 「给一个问题立一个答案」。最小面:
  - `card create (--card <cid> | --question '<q>') --answer '<claim>' [--cite <sid>:<indexes> ...]` → 没给卡就先建卡(新问题);`--answer` 落成这张卡下的一个 Position(引一个去重 Claim)。
  - `card view <card_id>` → 问题 + 它所有 Position(各自 credence / 顶踩 / 沉浮 / 治理),`accepted` 高亮。
  - **顶/踩走 review**:`memory.talk review <position_id> +1 --cite <sid>:<indexes>`(复用 v3 review,target 从 card 变 position)。
- **抽卡仍走 explore 工作台**(§6):`card create` 在 explore 目录里跑,产物盖 `explore_id` 戳(沿用 [explore.md](../v3/explore.md) 的关联机制,产物类型换成 v4 卡)。
- **insight 端点**:`memory.talk insight` / `/v3/insights`(步骤一改名而来),只读 + 搜索为主。

> 面的细节(flag 表、输出、退出码)等设计敲定后另起 `docs/cli/v4/` / `docs/api/v4/` / `docs/structure/v4/`,本稿只立机制。

---

## 11. 顺带回答两个问题

- **这是在训练模型吗?** 从 session 炼这张图(结构 + 参数)确实是**图模型归纳**(score-based 结构学习,评分 = 拟合 − 复杂度,正是负自由能那套),但**不是在训 LLM**——全程**前向推理 + 外部图更新,权重不动**。「训练一个图模型」成立,「训练那个 LLM」不成立。
- **为什么这条路现在成立?** 基座被冻死、闭源、不给碰,「懂用户」只能放进能碰的外部那半——**这张图:可读、可改、可删、跨基座可移植**。代价是它是**上下文级个性化**(受检索质量 / context 窗口 / context 忠实度制约),不是内化——而这恰恰也是它**可移植、可审计**的来源。

---

## 12. 诚实边界 + 待定

**全篇最容易写错、也最关键的三条**(实施时必须守住):

1. **沉默 ≠ 确认**:沉默只动 salience,不动 credence;校验只认真·支持/反驳。
2. **staleness ≠ wrongness**:「不该用」有两个独立来源(过期 / 位错),都不等于「错」。
3. **惊讶 grounding 在「检索没着落」,不是「LLM 生成了 question」**:否则整套退化成 confabulation 发生器。

**命名**:易经「位」= **Scope**(适用域门禁)≠ IBIS 的 **Position**(卡节点)。

**易经四维的真实成分**:大半是给已有概念起名(时↔staleness、势↔v3 的 `recall_count`+`read_count`、变↔lifecycle+resurrect),**真增量只有 Scope 和 fork**。v3 **没有** `salience` / `validity` 这种字段——它只有 Review(`review_up/down/neutral`,质量)、Read(`read_count`,engagement)、Recall(`recall_count`,popularity,0.9.0 起 derived)三轴 + 公式里的 `age_days`。

**风险清单**(实施时各自要有对策):

| 风险 | 对策方向 |
|---|---|
| why 的 confabulation | 低 prior、可证伪;惊讶 grounding 在检索 miss(§6 命门) |
| survivorship bias | 记 base rate(惊讶要除以「本可惊讶」的分母) |
| validator 过拟合 | 校验器别只学某一类证据 |
| 结构过拟合 | score 里加 complexity 正则(负自由能那套) |
| 纯不可变事实硬塞进图 | 纯事实可不进图、直接检索 |
| 关系 / 顶踩自动标注不可靠 | `card_links.type`、review `score`(顶/踩)的自动标注要有置信度 + 人工兜底 |

**待定(本稿没敲死的)**:

- Claim 去重用近重检测(embed)还是归一化文本精确匹配。
- **`scope`(位)该挂 Position 还是 Card**:适用域更像是「问题」的属性(卡级),但个别答案也可能有自己的适用域。本稿先挂 Position,卡级 scope 留作可能的上提。
- **`card ≡ issue` 1:1 是否永远成立**:同一个问题被不同框架问出来,要不要拆两张卡、还是靠 `replaces` / `related` 边连起来。
- 图是否值得 file-canonical:边/治理是重关系查询,纯 SQLite 可能更顺;文件罐主要为可移植/审计,card/claim/position 仍受益(§8 的切分是初稿)。
- §9 步骤一里 `card_`→`insight_` id 重写是一次到位还是拆段(降风险开关)。
- `momentum` / `credence` 的具体更新公式、`half_life_days` 衰减形态(留给 search-ranking 的 v4 版)。
