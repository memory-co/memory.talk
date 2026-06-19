# session annotation — 以写代读的逐 round 标注(v4 设计)

> **状态:设计提案,未实施。** 这是 v4 抽卡的**写路径前端**:总结一个 session 时,不让 AI 整段扫一遍就下结论(必走神),而是**逐 round 标注(annotation)**——**以写代读**,逼它真读;标注里用 `#问题` 把问题就地标出来,写入时**自动建卡 / 关联老卡**。于是「建卡」不再是一个单独的、容易脑补的步骤,而是**认真读的自然副产物**。
>
> 跟 [card.md](card.md) 的关系:card.md §6 讲写路径的**逻辑**(旁白→惊讶→question、命门 = 惊讶 grounding 在检索);**本篇讲它落地成什么 ergonomics** —— annotation 就是那个「旁白」,`#问题` 就是那个 question,「新卡 vs 关联」复用 card.md §6 的三岔。

相关:
- card 设计(问题图 + 写路径逻辑,本篇是它的写路径前端): [card.md](card.md)
- explore 抽卡工作区(在先验 session 上跑标注的工作台): [../v3/explore.md](../v3/explore.md)
- session rounds 写入(append-only;annotation 挂在 round 上,不改 round): [../v3/session-rounds-write.md](../v3/session-rounds-write.md)
- file-canonical 模式(annotation = sidecar jsonl + SQLite 索引): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)

---

## 1. 问题:整段总结必走神 —— 用「以写代读」治

把一个几十轮的 session 丢给 AI、让它「总结出 cards」,它会**走神**:扫读、跳读、脑补,漏掉真正有信息的轮次,还容易把没发生的事总结进去(confabulation)。根因是**读和写脱钩**——它不必逐轮证明自己读过,就能产出一段看似合理的总结。

**以写代读**(用写驱动读):给**每个 round** 产一条 **annotation**。你没法给 round 37 写标注却没读 round 37——**标注是「读过」的证据**。把「总结」从一次性顶层扫读,改成**自底向上、逐轮沉淀**,走神的空间被压没了。

| | 整段总结(v3 抽卡) | 逐 round 标注(本篇) |
|---|---|---|
| 读写关系 | 脱钩:扫一遍 → 直接产 card | 绑定:每轮一条标注 = 强制逐轮读 |
| 失败模式 | 走神 / 跳读 / confabulation | 想脑补也得先逐轮落字 |
| 产出粒度 | 顶层几张 card | 每轮 annotation,卡是副产物 |

> **逐 round 标注 ≠ card.md §6 否决的 v0**。v0 的毛病是「每条旁白都想直接变成 card」→ 噪声。这里**标注本身不变卡**:只有标注里 `#` 出来的问题、且经检索判为**新问题**(miss)才建卡(§3),噪声在下游被过滤掉。每轮都标,是为了**以写代读防走神**,不是把每轮都当信号。

---

## 2. annotation 是什么:逐 round、append-only、可标很多遍

- **逐 round**:标注挂在 `(session_id, round_index)` 上,一轮一条(或多条)。
- **append-only**:标注**只增不改**(跟 card / review / session 一个不变性)。改主意 = 追加新的一条,不覆盖。
- **可标很多遍(第 1 遍 → 第 2 遍 → …)**:整段对话可以被**反复重读标注**。后一遍带着更多 session 上下文 / 更多已建的卡回头看,**常常冒出前一遍没有的新感悟**——所以**一遍存一个文件**(`annotations/pass-N.jsonl`,§5),越后面的往往越深。
- **内容是自由的「感悟」**:为什么有这段对话、它在干嘛、我意识到什么。其中**问题用 `#` 就地标出来**(§3)。

> 为什么允许标很多遍:认知是**回看才长出来**的。第一遍读 round 37 可能只觉得「在配 pty」;建了几张卡、读完后面几轮再回看,才意识到「#为什么 pty 会让用户想到 tmux」。append-only 多遍标注把这个**逐步加深**的过程**留痕**,而不是只存一个终态。

---

## 3. `#问题` → 自动建卡 / 关联老卡

标注里只要冒出一个问题,就用**类 tag 的 `#` 语法**就地标:

```
配 pty 的时候用户突然提了 tmux。#为什么 pty 会让用户想到 tmux
他其实想要的是「可重连的会话」,而不是 pty 本身。
```

写入这条 annotation 时,系统:

1. **解析**出所有 `#…` 问题(`#` 起头、到行尾;行内多个用 `#{…}`)——于是「这条标注里有几个问题」是**自动数出来的**,不靠 AI 自己报。
2. 每个问题走 [card.md §6](card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question) 的三岔(embed 问题 → 撞 `cards` / issue 向量库):
   - **新问题(检索 miss)→ 建一张新卡**(还没有答案、在等答案)。
   - **老问题(检索 hit)→ 关联**到那张已有卡(annotation ↔ card 连上;**不动老卡任何分数**——相关性只在召回时算,见 [card.md §3](card.md#3-第二推credence--唯一存储的质量轴相关性只在召回时算))。
   - 两种情况都**记一条 `card_sessions`**(`card_id` + `session_id` + 这条 round 的 `index`):这就是「这个 session 的这条旁白**启发/碰到**了这张卡」的出处记录([card.md §8](card.md))。
3. 把 annotation ↔ card 的关联**写进这一行的 `questions[]`**(`card_id` + `is_new`:建了新卡还是关联老卡)——这是 **canonical**(file,§5);SQLite 里的 `card_sessions` 表(card.md §8)就是**从这些 `questions[]` 派生出来的可 join 索引**(card↔session,反查「这个 session 启发了哪些卡」)。

**这一步把「判断惊讶」从 AI 手里拿走了**:AI 只管**读 + 自然地标问题**;「这是不是个新问题(= 惊讶)」由**检索**算(miss = 新卡)。这正是 [card.md §6 命门](card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question) 最自然的落地——**惊讶 grounding 在检索,而不是 AI 自评**。于是建卡**非常自然**:你认真读、随手标问题,卡就长出来了。

---

## 4. 多遍标注 ↔ 卡的生命周期

`#问题` 建的卡一开始**只有问题、还没答案**。答案(Position)也从标注里长出来:

- **第一遍**:`#为什么 pty 会让用户想到 tmux` → 建一张**还没答案的卡**。
- **后面的轮 / 后面的遍**:标注里写出「他其实要的是可重连会话」——这是对那张卡的一个**答案**,落成它底下的一个 **Position**(答案文本内联在 Position 上),卡从「只有问题」变成「有候选答案」。
- 再有别的证据 顶/踩 这个 Position(review),按 `credence` 排序——回到 [card.md §3](card.md#3-第二推credence--唯一存储的质量轴相关性只在召回时算) 的校验机制。

所以一条龙都长在「逐 round 标注」这个自然动作上:**标注提问 → 建卡(只有问题)+ 记 `card_sessions` 出处;标注/后续答它 → Position;证据顶踩 → credence**。

---

## 5. 存储:跟 round 正文一样,file-canonical、不进 SQLite

annotation 是**大段自由文本**,量不小——所以**和 `rounds.jsonl`(round 正文)一个处理法**:**落文件、不进 SQLite**(v3 早把 `rounds_index` 表删了,round 正文只活在 `rounds.jsonl`)。一次「重读一遍」= 一个文件,append-only。

```
sessions/<source>/<sid[0:2]>/<sid>/
  rounds.jsonl              ← v3:round 正文(canonical · append-only)
  annotations/
    pass-1.jsonl            ← 第一遍读这段对话的标注(每行 = 某 round 在这遍的标注)
    pass-2.jsonl            ← 第二遍重读……新感悟进新文件,旧文件不动
    …
```

一行 = 某 round 在这一遍的标注:

```json
{"round_index": 37,
 "text": "配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux\n他其实想要可重连会话。",
 "questions": [{"raw": "为什么 pty 会让用户想到 tmux", "card_id": "card_01j…", "is_new": true}],
 "created_at": "2026-06-16T08:30:00Z"}
```

规则(照搬 round 正文那套不变性):

- **一遍一个文件**:`pass-N.jsonl` = 第 N 遍**重读整段对话**的产物。**最高编号 = 当前可追加;更低的已冻结**(再有新感悟 → 开下一遍)。每个 done 的 pass 文件天然不可变,还能 diff「这遍比上遍多悟到什么」。
- **可稀疏**:一遍里可能只重标了几个有新感悟的 round——`pass-N.jsonl` 只放这遍真写了的那些行。
- **append-only**:跟 `rounds.jsonl` 一样,只追加,从不改既有行。
- **不进 SQLite、也不进向量库**:annotation 本身不是检索单元;进 `cards` 向量库的是它 `#` 出来的**问题(卡)**,卡走正常 card 写路径落 SQLite。
- **annotation ↔ card 的链就写在那一行的 `questions[]` 里**(`card_id` / `is_new`),**不另起 SQLite 表**。以后若要「按 card 反查是哪些标注提出来的」,跟 v3 从 `rounds.jsonl` 回填 `last_round_update_time` 一个路子——**扫 `annotations/*.jsonl` 派生**即可,不必常驻一张表。

> **命名小注**:文件名写 `pass-N.jsonl` 而不是 `vN.jsonl`——本仓 `v` 已被**迁移框架版本号**和**产品代号 v3/v4** 占了两层意思,annotation 的「第几遍」用 `pass-N` 不容易混。结构跟你说的一样(一遍一个文件),只换了个不撞名的前缀。

---

## 6. 与 v3 / card / explore 的关系

- **card.md**:本篇是 card 写路径的**前端 ergonomics**;「新卡 vs 关联」的判定、卡 / Position / credence 全在 card.md,本篇不重复,只负责「从认真读里**自然冒出** `#问题`」。
- **explore.md**:explore 是**在先验 session 上跑标注**的工作台——你在 explore 目录里逐 round 标注先验会话,`#问题` 建 / 连卡,产物盖 `explore_id` 戳。annotation 就是 explore 里「抽卡」的那个具体动作。
- **v3 session / round**:annotation 按 `round_index` 指回现成的 `rounds.jsonl`,**不改 round 本身**(round 仍 append-only);annotation 是 session 目录下**新增的 `annotations/` sidecar**(跟 `rounds.jsonl` 并列),不动 v3 既有结构、也不进 SQLite。
- **v3 tag**:`#问题` 是**类 tag 的就地标记**,但语义不同——v3 `key=value` tag 是死字符串;`#问题` 写入时被**解析成卡 id**(建 / 连),是活的。

---

## 7. 诚实边界 + 待定

- **核心价值是「以写代读」,不是标注本身**:annotation 的存在意义首先是**逼 AI 逐轮真读**(防走神),其次才是留痕。哪怕标注写完没人再看,这个 forcing function 已经赚到了。
- **`#` 不判惊讶,检索才判**:AI 标 `#问题` 只是「我这觉得有个问题」;到底是不是**新**卡(惊讶)由检索 miss/hit 决定(card.md §6 命门)。别让 AI 自己说「这是新发现」。
- **别把走神搬到标注里**:逐 round 标注能防顶层扫读的走神;但若允许「一条标注糊一大段多轮」,走神会**搬家**。约束:一条 annotation 对应**一个 round**。

**待定**:

- **`#问题` 分隔符**:`#…` 到行尾(贴合本例)还是 `#{…}` 包起来(行内更稳)。初稿:行尾默认 + `#{…}` 行内。
- **同一问题的归一化**:`#为什么 pty 会让用户想到 tmux` 和 `#pty 为啥让人想到 tmux` 该不该 match 到同一张卡——靠 embed 近重还是更严的判定,本质是 card.md §6「`#` 问题撞到哪张卡」的匹配阈值。
- **`pass` 怎么触发**:第二遍标注是人 / AI 主动发起,还是系统在「新建了 N 张卡后」提示回看?留作 explore 工作流细节。
- **标注的最小产率**:是否每个 round 都必须有标注(强制逐轮),还是允许「这轮无话可说」跳过——但要显式记「看过、无标注」,别和「没看」混。
