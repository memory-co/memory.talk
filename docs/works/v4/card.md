# card — 被治理的问题图(v4 设计)

> **状态:设计提案,未实施。** 这是 **v4 的 card**:一张卡不再是「一句陈述」,而是「**一个问题 + 它的若干答案(竞争中的候选)**」,所有卡连成一张**被治理的问题图**。
>
> **它不改 v3 的卡,而是另起一代。** v3 现有的那套卡(`insight` 字段 + 论坛动力学 stats)**整体改名成 `insight`、数据保留、后续慢慢下掉**——把 `card` 这个名字腾出来给本设计。三者关系见 [§0](#0-三个名字v3-card--insight--v4-card)、迁移见 [§9](#9-与-v3--insight-的共存与迁移)。
>
> 本稿走的是「从最朴素的 card 出发、被一个个具体问题推着长成什么形状」的叙事:IBIS、易经治理(位/变)这些名字,都是走到那一步才出现。

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
| **v4 card** | 本稿:一张卡 = **一个 Issue(问题)+ 若干 Position(答案候选)**;哪个答案胜出靠 review 顶/踩(credence)竞争;卡连成被治理的问题图 | 新建,**复用腾出来的 `card_` 前缀 + `card` 命令** |

> 一句话:**v4 把"陈述卡"升级成"问答卡 + 问题图 + 治理层"。** v3 的卡没死,只是退到 `insight` 这个名字下慢慢退场。

---

## 1. 起点:最朴素的 card 会撞的四堵墙

最朴素的做法,也正是 v3 在做的:`session → 抽一句 insight → 存起来 → 检索时注入 context`。

它会连撞四堵墙——本稿四次「推」各自就是在拆这四堵:

| # | 墙 | v3 的痛点 | 哪一推拆它 |
|---|---|---|---|
| 1 | **卡是孤立陈述** | 难索引、难关联,还互相矛盾:「用户喜欢简洁」vs「用户有时要详细」谁说了算? | [§2 问答化](#2-第一推card--一个问题--它的若干答案) + [§4 IBIS](#4-第三推问题连成图--这套东西叫-ibis) |
| 2 | **「对不对」和「现在相不相关」搅在一起** | 一张卡被频繁 recall ≠ 它被验证过;`review_count` 和 `recall_count` 混在一个沉浮公式里 | [§3 只存 credence](#3-第二推credence--唯一存储的质量轴相关性只在召回时算) |
| 3 | **凭什么信一个答案** | 从一句话抽出的断言,可能只是模型臆测,没有证据链 | [§3 credence ← review 证据](#3-第二推credence--唯一存储的质量轴相关性只在召回时算) |
| 4 | **卡会过期、会被场景误用** | 去年的「住杭州」、投资立场卡跑去给育儿建议;v3 只有 `age_days` 一个弱信号 | [§5 位/适用域](#5-第四推给卡装上治理--位适用域-变生命周期) |

---

## 2. 第一推:card = 一个问题 + 它的若干答案

针对墙 1。与其存陈述「用户喜欢简洁」,不如存「**用户偏好什么回答风格?**」这个**问题**,底下挂上**若干候选答案**——卡变成「**一个问题 + 它的多个答案**」。

为什么这步对:

- **问题是天然的索引**:一个问题就是它那些答案的*适用条件*。检索时拿当前 context 去**撞问题**(而非撞陈述),命中率和精度都更高。
- **一个问题可以有多个答案在竞争**:哪个答案更好,**不靠创建时拍板**,而是后面用 review 顶/踩(credence)**竞争**出来(§3)。
- **答案文本就内联在 Position 上**:不单独建 Claim 节点、不跨 Position 共享去重——简单优先。(真出现「同一答案挂多个问题」的需求,再提升成共享节点,见 [§12](#12-诚实边界--待定)。)
- **没答的问题本身有价值**:一张还没有任何答案(Position)的卡,就是个**还在等答案的问题**——它不必被「解决掉」,所以也**不需要 open/closed 这种状态**。

于是一张 v4 卡 = **一个 Issue + 若干 Position**,涉及两种对象 + 一种复用 v3 的信号:

| 对象 | 是什么 | 角色 |
|---|---|---|
| **Card ≡ Issue** | 卡的那个**问题**(一张卡 = 一个问题,1:1) | **检索单元 + 图节点**(embed 问题;卡↔卡连边见 §4) |
| **Position** | 卡底下的**一个候选答案**(答案文本 `claim` 内联在它身上) | **被顶/踩、按 credence 排序的那个东西**——治理 + credence 都挂它身上 |
| **Review** | 带 session 证据(`indexes`)的一次**表态**(`argument` ∈ `+1`/`0`/`−1` = 支持/中立/反对),**target = Position**;沿用 v3 review | 既是「证据」也是「表态」(§3);**`argument≠0` 的 review = 一条 IBIS Argument** |

> **别再把 Position 当成整张卡**(这是上一稿的错):**card = 一个 Issue + 若干 Position**。Position 是**答案候选**,卡是**问题 + 这些候选的集合**。「哪个 Position 是这张卡的答案」不是写死的,是 review 顶/踩(credence)**浮**出来的(`accepted` = credence 最高的 active Position,≈ Stack Overflow 的采纳答案)。
>
> **Review = 带 session 证据的表态;Argument = 其中带方向的那些**:对一个 Position 的一次反应,就是一条 **Review**(`indexes` 证据 + `argument` 方向)。`argument` 有**三个值**:`+1`(支持/顶)、`−1`(反对/踩)、`0`(中立——证据相关、但不站队)。**`argument≠0` 的 review 就是一条 IBIS Argument**(pro/con);`argument=0` 是中立观察,不是 argument。对象**沿用 v3 的 `review`**(v3 review 本就是「证据 + score ±1/0」),不强行压成纯 pro/con——因为中立确实会出现(§3 末)。
>
> **跨卡关联只走 `card_links`(§4)**:答案文本内联、不共享,所以没有「共享 claim」那条隐式关联路径;Position 之间也**不直接结网**(图的骨架在卡/问题层)。

---

## 3. 第二推:credence —— 唯一存储的质量轴(相关性只在召回时算)

针对墙 2、墙 3。墙 2 的病根是 v3 把「这个答案**对不对**」和「这个主题现在**相不相关**」搅进同一个沉浮公式。v4 把这两件事彻底分开,而且**只存前者**:

- **对不对 → `credence`(存)**:每个 Position 一个 `credence`,只由**对它的 review 顶/踩**(`argument`=±1,带 session 证据)推动——顶抬、踩压。这是 Position 上**唯一的质量轴**,可重算(= `up_count` / `down_count` 的函数)。
- **相不相关 → 召回时算(不存)**:一个答案现在相不相关,**不写回任何字段**,而是**召回那一刻**拿当前 context 去撞卡的问题(向量 + FTS,§7 读路径)现算。所以**没有** `salience` / `momentum` 这种存储态——相关性是检索的产物,不是 Position 的属性。

**关键:校验机制照搬 v3 的 review(顶/踩),只下放到 Position。** v3 的 review 那套**原封不动**,只把 target 从 `card_id` 换成 `position_id`:

- `up_count` / `down_count` / `neutral_count` **就是这个 Position 收到的 `argument` = `+1` / `−1` / `0` 的 review 数**(顶 / 踩 / 中立,对应 v3 的 `review_up` / `review_down` / `review_neutral`)。`credence` 只是前两者的函数(顶抬、踩压;沉默和中立都不动 credence)。
- **`accepted`(本卡当前答案)= `credence` 最高的 active Position**——不靠创建时拍板、也不靠一条单独的排序量,就是**被验证得最好的那个浮上来**(≈ Stack Overflow 的采纳答案)。
- **去掉「势 / momentum」的理由**:v3 的「势」本质是把 recall/read 回写进一个分数再拿它排序。但相关性每次召回都能由检索现算,**回写是冗余**;而且一旦回写,「频繁被 recall」就会污染「被验证过」——正是墙 2。v4 **不回写**:recall/read 不进任何存储字段,召回排序直接用检索相关性 + `credence`。

最容易写错、也最关键的一点:**沉默 ≠ 确认,也 ≠ 否定**。后续对话**绝大多数**对一个 Position 是沉默的(主题压根没再出现):

- 沉默**什么存储态都不动**——既不抬也不压 `credence`(相关性根本不存,下次相不相关召回时再算)。
- 校验**只认**真·顶 / 真·踩(带证据、`argument≠0` 的 review),无关的、中立的不算(§6 写路径靠「检索匹配」判定相不相关)。

> **对照 v3**:v3 的 review/read/recall 挂在**整张卡**、还揉进一个沉浮公式;v4 **只把 review(顶/踩)下放到 Position 变成 `credence`,把 read/recall 整个踢出存储**:同一个问题下的**不同答案各自被顶踩、按 credence 竞争**,于是「这个问题到底哪个答案对」第一次有了**结构**(竞争 + 采纳),而不是糊在一张卡、也不被「热不热」干扰。

> **中立(`argument=0`)堆多了 → 可能衍生新 Position**:一条中立 review = 「证据跟这个问题相关,但不站现有任何答案的队」。一张卡积累了一批中立,说明**现有答案没接住这些证据**——它们可能在为一个**还没被说出来的答案**背书。于是把这堆中立**聚类 → 提一个新 Position**,这些 review 再以 `+1` 重挂到新答案上。这是 §6「检索 miss → 新卡」在**卡内部**的版本(中立 = 「对现有 Position 全 miss」)。两点要守住:① **触发是离线启发式**(人/LLM 看这堆中立够不够攒成一个答案),不自动;② 分清「对某答案纯属拿不准」(只加不确定性,不衍生)和「证据其实指向别的答案」(才衍生)。中立**不动 credence**;中立 ≠ 沉默(沉默 = 没 review)。

---

## 4. 第三推:问题连成图 —— 这套东西叫 IBIS

针对墙 1 的后半(关联)。卡已经是「问题 + 多个答案 + 证据」,问题与问题之间显然还互相关联:一个问题是另一个的细化、一个答案会引出新问题……

把这些关联显式化之后会发现:**被 card 的问题独立推出来的东西,学术上早有名字——IBIS(Issue-Based Information System)**。它的三类节点 Issue / Position / Argument 正好都对上(**Argument = `argument≠0` 的 review**,见 §2),问题之间的关系也正好是它那套。直接借本体,不重造轮子。

**什么连什么**:**卡 ↔ 卡**(= `issue ↔ issue`,因 card ≡ issue)是**关联主干**;`position` 之间不直接结网。

| 边 type | 含义 | 方向 |
|---|---|---|
| `specializes` | A 是 B 的更窄版(子问题,**DAG 非树**) | 有向 |
| `suggested_by` | A 被某节点引出来(出处 / 因果);**对端可为 Position**(答案也能勾出新问题) | 有向 |
| `questions` | A 质疑 B 的前提 / 框架 | 有向 |
| `replaces` | A 重述并取代 B(**保留历史**,不删 B) | 有向 |
| `related` | 兜底泛关联 | 无向 |

> IBIS 关系集**不完备**,可按需补 `depends_on` / `part_of`。存储上是**两套抄**:**本体抄 IBIS**(节点 + 边的类型学),**投票 / 采纳那套机制抄 Stack Overflow**(**review 顶/踩 → credence**;`accepted` 采纳 = 浮上来的那个答案)。这些 issue↔issue 的边落地为 `card_links`(§8):**主体卡 + `target_id`**(非对称 from/to)、**五类型全多值**(同一卡同一类型可多条,如 specializes 多父 → 统一边表、不内联成列)、`target_id` 前缀多态(`suggested_by` 可指 `pos_` Position)。

---

## 5. 第四推:给卡装上治理 —— 位(适用域)+ 变(生命周期)

针对墙 4 的后半(场景误用)。IBIS 给了**结构**,但没说一张卡**在哪能用、怎么变迁**。把这层显式建出来,对上两个工程维度——助记叫「位 / 变」(去魅:就是 *适用域门禁 / 生命周期*,「易经」只是助记标签):

> **原设计有四维「时位势变」,本稿砍到两维**:**时(过期/半衰)**和**势(沉浮排序量)已删**——时间过期暂不建模,相关性改由召回时检索现算(§3),不回写成字段。墙 4 的「过期」那半因此暂时无人接(只能靠本节末的 **变/lifecycle** 离线下掉),见 §12。

| 维度 | 字段 | 干什么 | 防的失败 |
|---|---|---|---|
| **位** scope | `Scope`:`domain × role × authority × layer` + `exclusions` | 适用域门禁 | 跨场景误用(投资卡去答育儿) |
| **变** change | 状态机:`active` / `forked` / `dormant` / `archived`(+ `superseded_by` / `forked_from`) | 生命周期 | 静默覆盖、认知史丢失 |

两个**最容易错**的要点:

1. **「不该用」≠「错」**。一张卡可以没被反驳、`credence` 还高,但**用错了场景**(位错),照样不该用。「不该用(位错)」和「对不对(credence)」是两件独立的事,别用 credence 去判该不该用。(注:v3 的「时间过期」也是「不该用」的一个独立来源,但本稿**不建模时间**,见 §12;过期暂时只能靠 **变/lifecycle** 离线下掉。)
2. **易经的「位」≠ IBIS 的 Position 节点**。这里的「位」是**适用域门禁**,本稿叫它 **Scope**;它和「Position(卡底下的答案候选)」是两回事,**别混**。
3. **这两维里真正比 IBIS 多出来的增量**:**位** = Scope/适用域 + exclusions(IBIS 没有适用域),和 **变**里的 **fork**(信念分叉时**分支而非覆盖**,保住认知史)。`change_state` 其余部分大半是给 lifecycle 起名。

**两条路径,别混**:

- 检索时,一张卡要过**位**这道门禁(适用域不符 / 命中 exclusions → 挡掉)才允许塑造回答(§7 读路径);幸存者按 `credence` 排序。
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

前面讲卡长什么样、怎么用;这节讲卡**怎么从对话里长出来**。下面是几种做法的取舍——**这是设计推理(考虑过什么、为什么否掉),不是跑过的版本**;尤其 logprob 那条**从没实现、也没有字段**,只是一条被划掉的岔路:

| 做法 | 怎么做 | 取舍 |
|---|---|---|
| 每条旁白都直接变卡 | 每个 round 写旁白,**每条旁白都落成一张卡** | **否**:绝大多数 round 平淡,**每条都变卡 = 噪声**(注意:噪声来自「都变卡」,**不是**来自「都标注」) |
| 只在「惊讶」的轮才动手 | 跳过平淡的轮,只标 / 只抽惊讶处 | 把问题推成「**怎么判一轮惊不惊讶**」;而且「让 AI 自己挑该读哪轮」恰恰是**走神的入口** |
| 用 logprob 测惊讶 | 带 / 不带用户模型两遍打分,`ℓ_model − ℓ_base` | **否(从没实现、无字段)**:Opus 接口给不了 logprob,挂本地打分器太重 |
| **每轮照标,但只有 `#问题` 经检索才建卡**(当前选定) | **每个 round 都写旁白**(以写代读防走神);标注**不直接变卡**,只有其中 `#问题`、且检索判为新问题(miss)才建卡 | **选它**:per-round 标注是 forcing function(**不是噪声**),噪声靠下游「检索过滤」掐掉;惊讶不靠 AI 自判,靠检索 miss。落地见 [session-annotation.md](session-annotation.md) |

> **纠正**:别把账算到「每轮都标」头上——噪声来自**每条标注都变成卡**,不是来自**每轮都标**。当前设计**就是每轮都标**(那正是 [session-annotation.md](session-annotation.md) 的「以写代读」核心),只是把「变不变卡」交给 `#问题` + 检索过滤;所以每轮标注非但不是噪声,反而是**防走神的关键**。

**命门**(否则退化成 confabulation):惊讶**不是**「生成了 question」(LLM 永远能生成 question),而是「**生成的 question 在图里找不到已被自信回答的对应**」。所以拿生成的 question 去 **issue 向量库检索匹配**,按结果分三岔:

| 检索结果 | 判定 | 动作 |
|---|---|---|
| **miss**(最近邻距离 > θ) | 真·新问题 | 建**新卡**(新问题),起 why→Q→A 的第一个 Position,`birth_surprise` = 距离 |
| **hit** 某卡、且它 `accepted` 的答案一致 | 不惊讶 | 给那个 Position 加一条 **`argument=+1` 的 review**(→ `up_count++`,轻推 credence) |
| **hit** 某卡、但与它现有答案**冲突** | **矛盾(最高价值)** | 给旧 Position 加一条 **`argument=−1` 的 review** + 在**同一张卡下新建一个竞争 Position** |

**惊讶幅度**(排序 / 预算用)用**检索距离**(question 到图里最近节点的 cosine)当代理,**也不用 logprob**。logprob 降为可选高保真层,大概率用不上。

> 写路径的上游工作台是 **explore**(先验/后验抽卡工作区,[../v3/explore.md](../v3/explore.md)):在先验 session 上跑这条「旁白→惊讶→question」抽出 v4 卡,用后验 session 回流证据(§7)。explore 的产物从「insight 卡」换成「v4 卡(问题 + 答案)」,工作台机制不变。
>
> **这条写路径落地成什么 ergonomics** —— 逐 round 标注(以写代读)+ 标注里 `#问题` 自动建卡 / 关联 —— 见 [session-annotation.md](session-annotation.md)。那篇是本节逻辑的**具体前端**:annotation = 旁白,`#问题` = question,新卡/关联复用本节三岔。

---

## 7. 读路径 + DTO

### DTO:Card + Position

一张卡 = 一个 **Card**(问题)+ 若干 **Position**(答案);治理(位 + 变)挂在 **Position** 上,Card 只管问题 + 连边:

```python
class Card(BaseModel):                      # = 一个问题(≡ Issue),图节点
    card_id: ID                             # card_<ulid>
    issue: str                              # 问题文本;检索锚点(embed 它)
    created_at: str
    # 卡↔卡的边(§4)单独存 card_links,不内联

class Position(BaseModel):                  # 卡底下的一个答案候选;被顶踩、按 credence 竞争的就是它
    position_id: ID; card_id: ID            # 属于哪张卡
    claim: str                              # 答案文本(内联在 Position,不单独建节点、不共享)
    # 校验轴(§3)= 这个 Position 的 review 顶/踩(argument ±1/0)
    credence: float = 0.5
    up_count: int = 0       # = argument=+1 的 review 数(顶)
    down_count: int = 0     # = argument=−1 的 review 数(踩)
    neutral_count: int = 0  # = argument=0 的中立 review 数(堆多了→衍生新 Position)
    accepted: bool = False                  # credence 最高的 active Position = 本卡当前答案
    cited_rounds: list[RoundRef] = []       # [{session_id, index}] 抽这个答案的出处
    # 治理:位 / 变(§5)
    scope: Scope                            # domain×role×authority×layer + exclusions
    change_state: Literal["active","forked","dormant","archived"] = "active"
    superseded_by: ID | None = None
    forked_from: ID | None = None           # 变:分支保留认知史
    birth_surprise: float | None = None     # §6 的检索距离
    created_at: str
```

`Review`(`target = position_id` + `indexes` + `argument`(`+1`/`0`/`−1`);沿用 v3 review,`argument≠0` 即 IBIS Argument)、`CardLink`(主体卡的边:`card_id` + `type` + `target_id`,对端 `card_` 或 `pos_`)各自是独立 BaseModel。**答案文本 `claim` 内联在 Position 上(不单独建 Claim 节点);治理只挂 Position;Card 只管问题 + 连边;证据/表态是 Review。**

### 读路径

```
召回   : context → embed → 撞卡的问题(向量 + FTS)→ 取命中卡底下的 Position
         (相不相关就在这一步由检索算清,不读任何存储字段)
位门禁 : 逐个 Position 过——context 的 domain/role/authority/layer 不在 scope 内,或命中 exclusions → 挡掉
排序   : 幸存 Position 按 credence 排序;一张卡通常只取最高的那个(accepted)
注入   : 幸存者按 credence 进 context
回流   : 用户在后续 round 顶/踩 → 一条 review(带证据,`argument` ±1/0)→ 动那个 Position 的 credence(= §6 写路径)
```

> **结构**(卡=问题+答案候选)决定能不能连、怎么连;**治理**决定何处可用、怎么变;**review 顶/踩(credence)**决定一张卡里哪个答案胜出;**写路径**决定它们怎么从对话长出来。

---

## 8. 存储:file-canonical 罐 + SQLite 瘦索引 + searchbase

沿用本仓 [file-canonical 模式](../v3/file-canonical-pattern.md):**文件罐是 canonical**(可移植 / 审计);**SQLite 是派生索引**(既照抄不可变字段供查询,也存可变运行态——跟 v3 `cards`/`card_stats` 一个路子);检索进 searchbase。

**不可变核 vs 可变运行态**:

- **不可变核**(create 即冻,canonical 在文件罐):Card 的 `issue`、Position 的 `(card_id, claim, cited_rounds, birth_surprise, created_at)`(`claim` = 答案文本)。
- **可变运行态**(SQLite 实时维护):`credence / up_count / down_count / neutral_count / accepted`、治理两维(位 + 变)、`card_links`。SQLite 同时**照抄一份不可变字段**供查询,崩了能从文件罐重建。

```
cards/<bucket>/<card_id>/card.json            ← canonical:issue + created_at(问题不可变)
cards/<bucket>/<card_id>/positions/<pid>.json ← canonical:claim(答案文本)+ cited_rounds + birth_surprise(答案核不可变)
                                                credence/治理/边/review = SQLite 派生运行态
```

> Position 的**文件**放在它所属卡的目录下(`cards/<card_id>/positions/`)——一张卡 = 一个问题 + 它的答案们,物理上聚在一起。**review 不进文件罐**(沿用 v3 review 的存法:有自己的 canonical),只在 SQLite 里 target 到 `position_id`。

**SQLite 派生索引 + 运行态**(v4 卡表是再后面一版迁移,见 §9):

```sql
CREATE TABLE cards (                       -- = 一个问题(≡ Issue),图节点
  card_id    TEXT PRIMARY KEY,             -- card_<ulid>(v4 复用 card_ 前缀;v3 已腾给 insight_)
  issue      TEXT NOT NULL,                -- 问题文本;检索锚点(进向量库)
  created_at TEXT NOT NULL
);
CREATE TABLE positions (                   -- 卡底下的答案候选;被顶踩、按 credence 竞争的就是它
  position_id    TEXT PRIMARY KEY,         -- pos_<ulid>
  card_id        TEXT NOT NULL,            -- 属于哪张卡(问题)
  claim          TEXT NOT NULL,            -- 答案文本(内联,不共享、不单独建表)
  cited_rounds   TEXT NOT NULL DEFAULT '[]',  -- 派生副本;canonical 在 positions/<pid>.json
  -- 校验轴 = 这个 Position 的 review 顶/踩(§3)
  credence       REAL    NOT NULL DEFAULT 0.5,
  up_count       INTEGER NOT NULL DEFAULT 0,   -- = argument=+1 的 review 数(顶)
  down_count     INTEGER NOT NULL DEFAULT 0,   -- = argument=−1 的 review 数(踩)
  neutral_count  INTEGER NOT NULL DEFAULT 0,   -- = argument=0 的中立 review 数(堆多了→衍生新 Position)
  accepted       INTEGER NOT NULL DEFAULT 0,
  -- 治理:位 / 变(§5)
  created_at     TEXT NOT NULL,
  scope          TEXT NOT NULL DEFAULT '{}',  -- 位:Scope JSON
  change_state   TEXT NOT NULL DEFAULT 'active',  -- active|forked|dormant|archived
  superseded_by  TEXT, forked_from TEXT, birth_surprise REAL
);
CREATE INDEX idx_pos_card ON positions(card_id);
-- review:对 Position 的带证据表态(沿用 v3 review;`argument≠0` 即 IBIS Argument),target 从 card_id 换成 position_id
CREATE TABLE reviews (
  review_id   TEXT PRIMARY KEY,            -- review_<ulid>
  position_id TEXT NOT NULL,               -- 表态哪个答案
  card_id     TEXT NOT NULL,               -- 冗余 = positions.card_id;源不可变(答案不换卡)→ 永不漂移,省「这张卡所有 review」的 join
  session_id  TEXT NOT NULL,
  indexes     TEXT NOT NULL,               -- session 证据(哪几个 round)
  argument    INTEGER NOT NULL,            -- 方向:+1 支持(pro)/ 0 中立 / -1 反对(con)
  comment     TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_reviews_position ON reviews(position_id, created_at DESC);
CREATE INDEX idx_reviews_card     ON reviews(card_id);
CREATE TABLE card_links (                  -- 主体卡的有向边(= IBIS issue↔issue,因 card≡issue)
  card_id    TEXT NOT NULL,               -- 主体卡(谁的边),不是对称 from/to
  type       TEXT NOT NULL,               -- specializes|suggested_by|questions|replaces|related
  target_id  TEXT NOT NULL,               -- 对端:多为 card_…;suggested_by 可为 pos_…(前缀自带类型,免 target_type 列)
  created_at TEXT NOT NULL,
  PRIMARY KEY (card_id, type, target_id)  -- 同一(主体, 类型)下可多条 → 五类型全多值;related 无向 → 写时规范化排序只存一遍
);
```

> `up_count` / `down_count` / `neutral_count` 就是 v3 `card_stats` 的计数器**搬到 Position**(`neutral_count` = v3 的 `review_neutral`,这回留着;**v3 的 `read_count` / `recall_count` 这套 engagement 计数 v4 不再存**——相关性只在召回时算,见 §3);`credence` 只由 ±1 派生(`argument=0` 不动 credence)。表态落 `reviews` 表(`argument≠0` 即 IBIS Argument)。

**searchbase**(复用 [searchbase 端口](../v3/searchbase-extraction.md),零侵入):

| collection | embed 什么 | 用途 |
|---|---|---|
| `cards` | `issue` | **检索主单元**(读路径撞 issue、写路径 §6 拿生成的 question 来匹配,都打它;v3 `cards` collection 已在 §9 改名腾出此名) |
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
| SQLite 表 | `cards` / `card_stats` / `card_source_cards` / `reviews` | `insights` / `insight_stats` / `insight_source_cards` / `insight_reviews`(腾出 `reviews` 给 v4) |
| LanceDB collection | `cards` | `insights` |
| id 前缀 | `card_<ulid>` | `insight_<ulid>`(连带重写 `insight_reviews` / `recall_event` / `source_cards` 里的引用) |
| 文件罐 | `cards/<bucket>/...` | `insights/<bucket>/...` |
| 代码符号 | `service/cards.py` 等 | `service/insights.py` 等 |

> **searchbase 侧不是「改名」是「拷贝」**:`AdminBackend` **没有** `rename_collection`(只有 create / drop / copy_rows / add·rename·drop_column,见 [migration.md](../v3/migration.md))。所以 LanceDB 的 `cards`→`insights` 走 `create_collection('insights')` + `copy_rows(cards→insights)` + `drop_collection('cards')`(在 `migrations/v3/up_searchbase.py`)。`cards` collection 是 flat 布局、只 embed `insight`(fields schema 空),原样搬即可;或干脆用 [index-backfill](../v3/index-backfill.md) 从文件罐重灌。
>
> **id 前缀重写是最重的一段**:`card_<ulid>`→`insight_<ulid>` 要一致改写**所有**跨对象引用——`insight_reviews.card_id`、`card_source_cards.{card_id, source_card_id}`、`recall_event.{returned_ids, skipped_ids}`(JSON 数组)、`search_log.response_json`,以及文件罐 `cards/<bucket>/` 的 bucket(= `card_id[5:7]`,前缀变了 bucket 跟着变)。**若想降风险可分两段**:先改名 CLI/API/代码/SQLite 表/collection,**`card_` id 前缀暂留**,把 id 重写单独作为后续一次迁移(属于「慢慢下掉」的一部分)。本稿倾向一次到位,把这个开关留给实施时定。

### 步骤二:v4 card 全新起(复用腾出来的名字)

insight 让出 `card` / `card_`(连 `reviews`→`insight_reviews`)之后,v4 在干净地基上建:`cards`(问题)/ `positions`(答案 + 内联文本,`pos_`)/ `reviews`(对 Position 表态,`review_`,`argument` ±1/0)/ `card_links`,**卡复用 `card_` 前缀 + `card` 命令**。**v4 与 insight 物理隔离**(不同表、不同 collection、不同前缀),互不干扰地共存。

### 步骤三:慢慢下掉 insight(后话,本稿不强求)

- insight **只读可搜**:老数据继续能 `search` / `read` / 回看,但**新抽卡只写 v4**。
- 可选**投影**:把每条 insight **投影**进 v4 图——一条 insight →(一张**卡** =「这条洞见在答的问题」+ 一个 **Position** = 洞见本身那个答案,其 `rounds`→`cited_rounds`;原 insight 的 review(`insight_reviews`)跟着 target 到这个 Position,成为 v4 review(`argument` = 原 `score`))。投影完的 insight 可 `archived`。
- 投影是渐进、可暂停的;投影策略 / 触发时机另案。

---

## 10. API / CLI 面

- **端点**(复数):`/v4/cards`(问题 + 它的 Positions)、`/v4/cards/{id}/positions`、`/v4/positions/{pid}/reviews`(表态 ±1/0)、`/v4/card-links`。读路径 `/v4/recall` 走「撞问题 → 取 Position → 位门禁 → credence 排序」。
- **CLI**:`memory.talk card`(v4 复用此命令),语义 = 「给一个问题立一个答案」。最小面:
  - `card create (--card <cid> | --issue '<问题文本>') --answer '<答案文本>' [--cite <sid>:<indexes> ...]` → 没给卡就先建卡(新建 issue);`--answer` 落成这张卡下的一个 Position(答案文本内联在 Position 上)。
  - `card view <card_id>` → 问题 + 它所有 Position(各自 credence / 顶踩 / 治理),`accepted` 高亮。
  - **表态走 review**:`memory.talk review <position_id> <+1|0|-1> --cite <sid>:<indexes>`(沿用 v3 review,target 从 card 变 position)。
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

1. **沉默 ≠ 确认**:沉默什么存储态都不动(相关性不存、只在召回时算),只有真·顶/踩动 credence。
2. **「不该用」≠「错」**:用错场景(位错)跟答案对不对(credence)是两件独立的事;别用 credence 判该不该用(时间过期那个来源本稿不建模,见下)。
3. **惊讶 grounding 在「检索没着落」,不是「LLM 生成了 question」**:否则整套退化成 confabulation 发生器。

**命名**:易经「位」= **Scope**(适用域门禁)≠ IBIS 的 **Position**(卡节点)。

**易经治理的真实成分**:本稿只留**位 / 变**两维。**真增量只有 Scope(适用域)和 fork**;`change_state` 其余是给 lifecycle 起名。原设计的**时(过期/半衰)**和**势(沉浮排序量)两维已删**——时间过期暂不建模,相关性改由召回时检索现算(§3),不再回写成字段。v3 本就**没有** `salience` / `validity` 字段——它只有 Review(`review_up/down/neutral`,质量)、Read(`read_count`,engagement)、Recall(`recall_count`,popularity)三轴 + `age_days`,v4 只继承其中的 Review。

**风险清单**(实施时各自要有对策):

| 风险 | 对策方向 |
|---|---|
| why 的 confabulation | 低 prior、可证伪;惊讶 grounding 在检索 miss(§6 命门) |
| survivorship bias | 记 base rate(惊讶要除以「本可惊讶」的分母) |
| validator 过拟合 | 校验器别只学某一类证据 |
| 结构过拟合 | score 里加 complexity 正则(负自由能那套) |
| 纯不可变事实硬塞进图 | 纯事实可不进图、直接检索 |
| 关系 / 顶踩自动标注不可靠 | `card_links.type`、review `argument`(`+1`/`0`/`−1`)的自动标注要有置信度 + 人工兜底 |

**待定(本稿没敲死的)**:

- **`scope`(位)该挂 Position 还是 Card**:适用域更像是「问题」的属性(卡级),但个别答案也可能有自己的适用域。本稿先挂 Position,卡级 scope 留作可能的上提。
- **`card ≡ issue` 1:1 是否永远成立**:同一个问题被不同框架问出来,要不要拆两张卡、还是靠 `replaces` / `related` 边连起来。
- 图是否值得 file-canonical:边/治理是重关系查询,纯 SQLite 可能更顺;文件罐主要为可移植/审计,card/position 仍受益(§8 的切分是初稿)。
- §9 步骤一里 `card_`→`insight_` id 重写是一次到位还是拆段(降风险开关)。
- `credence` 的具体更新公式(顶抬 / 踩压形态;留给 search-ranking 的 v4 版)。
- **时(过期)/ 势(相关性回写)整个不建模**:原「时位势变」只落地「位 / 变」。日后若「过期假设支配当下」真成问题,再把 `expires_at` 这类最小门禁加回 Position;相关性目前一律召回时现算、不存。
- **中立 review 攒到多少 / 多相似才触发「衍生新 Position」**(§3 末的离线启发式阈值);跟 §6「检索 miss → 新卡」是否共用一套触发逻辑。
