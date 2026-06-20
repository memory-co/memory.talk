# session mark — 以写代读的逐 round 标记(v4 设计)

> **状态:设计提案,未实施。** 这是 v4 抽卡的**写路径前端**:总结一个 session 时,不让 AI 整段扫一遍就下结论(必走神),而是**逐 round 提交一份 mark**——**以写代读**,逼它真读;mark 里用 `#…？` 把问题就地标出来,写入时**自动建卡 / 关联老卡**,卡的出处(`card_source`)**精确指向那条 mark**。于是「建卡」不再是一个单独的、容易脑补的步骤,而是**认真读的自然副产物**。
>
> 跟 [card.md](card.md) 的关系:card.md §6 讲写路径的**逻辑**(旁白→惊讶→question、命门 = 惊讶 grounding 在检索);**本篇讲它落地成什么 ergonomics** —— mark 就是那个「旁白」,`#…？` 就是那个 question,「新卡 vs 关联」复用 card.md §6 的三岔,出处落 [`card_sessions`](../../structure/v4/card-session.md)。
>
> 本篇取代旧设计 `session-annotation.md`(annotation→**mark**、自由 jsonl 行→**每轮一份 YAML 数组**、`#问题` 到行尾→**`#…？` 收尾**、出处指 (session,round)→**指 mark id**)。

相关:
- card 设计(问题图 + 写路径逻辑,本篇是它的写路径前端): [card.md](card.md)
- 出处数据结构(`card_sessions`,本篇把它改成指 mark): [../../structure/v4/card-session.md](../../structure/v4/card-session.md)
- explore 抽卡工作区(在先验 session 上跑 mark 的工作台): [../v3/explore.md](../v3/explore.md)
- session rounds 写入(append-only;mark 挂在 round 上,不改 round): [../v3/session-rounds-write.md](../v3/session-rounds-write.md)
- file-canonical 模式(mark = sidecar 文件 + SQLite 派生索引): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)

---

## 1. 问题:整段总结必走神 —— 用「以写代读」治

把一个几十轮的 session 丢给 AI、让它「总结出 cards」,它会**走神**:扫读、跳读、脑补,漏掉真正有信息的轮次,还容易把没发生的事总结进去(confabulation)。根因是**读和写脱钩**——它不必逐轮证明自己读过,就能产出一段看似合理的总结。

**以写代读**(用写驱动读):给**每个 round** 提交一份 **mark**。你没法给 round 37 写 mark 却没读 round 37——**mark 是「读过」的证据**。把「总结」从一次性顶层扫读,改成**自底向上、逐轮沉淀**,走神的空间被压没了。

| | 整段总结(v3 抽卡) | 逐 round mark(本篇) |
|---|---|---|
| 读写关系 | 脱钩:扫一遍 → 直接产 card | 绑定:每轮一份 mark = 强制逐轮读 |
| 失败模式 | 走神 / 跳读 / confabulation | 想脑补也得先逐轮落字 |
| 产出粒度 | 顶层几张 card | 每轮 mark,卡是副产物 |

> **逐 round mark ≠ card.md §6 否决的 v0**。v0 的毛病是「每条旁白都想直接变成 card」→ 噪声。这里**mark 本身不变卡**:只有 mark 里 `#…？` 出来的问题、且经检索判为**新问题**(miss)才建卡(§3),噪声在下游被过滤掉。每轮都标,是为了**以写代读防走神**,不是把每轮都当信号。

---

## 2. mark 是什么:每轮一份 YAML、数组、append-only

**一个 round = 一份完整的 mark 提交**,格式是 **YAML**:顶层 `description`(这份 mark 的场景:为什么读这段、读的时候在想什么)+ `marks`(数组,元素是一条 mark〔字典〕,字段 `id` + `mark`)。

```yaml
# round 37 的 mark 提交(= sess_def456 的 m1、m2 两条 mark)
description: 在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么
marks:
  - id: m1
    mark: |
      配 pty 的时候用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？
      他其实想要的是「可重连的会话」,而不是 pty 本身。
  - id: m2
    mark: 这段其实在排查 EMFILE,跟句柄上限有关。
```

- **每轮一份**:一次提交对应**一个 round**(挂在 `(session_id, round_index)` 上)。一份提交里可以有**多条 mark**(`marks` 数组),各自一个 `id`、一段 `mark` 内容。
- **`description` = 这份 mark 的场景**:顶层一句话,描述「为什么在这轮做这次标注、读的时候带着什么问题 / 上下文」。它是**这次提交的元信息**,跟着这份 mark 落盘(§6),让事后回看能秒懂当时心境,而不只是看到孤立的几条感悟。
- **`id` = `m<n>`,mark 不是一等 id**:mark **附属于 session**,id 形如 **`m1` / `m2`**(`m` + session 内递增序号),寻址 **`<session_id>#<id>`**(如 `sess_def456#m1` = 这个 session 的**第 1 条 mark**)。**不是** `mark_<ULID>` 那种独立前缀 id。`m<n>` 直接当**文件名**落盘(`marks/m1.yaml`,§6)。**`card_source` 就指 `(session_id, id)`**(§4)——这是「出处指 mark 而非仅 session」的落点。读它走 `read sess_def456#m1`(§7)。
- **`mark` = 自由的「感悟」**:为什么有这段对话、它在干嘛、我意识到什么。其中**问题用 `#…？` 就地标出来**(§3)。
- **append-only**:mark **只增不改**(跟 card / review / session 一个不变性)。改主意 = 追加新的一条(新 `m<n>`),不覆盖旧的;`m<n>` 序号在 session 内单调、不复用。
- **可标很多遍**:整段对话可被**反复重读**,后一遍带着更多上下文 / 更多已建的卡回头看,常冒出新感悟——**就接着往后加 mark**(`m5`、`m6`…,§6),越后面往往越深;靠序号 / 时间戳就能看出哪些是后补的,不另起「遍」的目录。

> 为什么 YAML + 数组:一轮里常常**不止一个感悟**(一个 `#…？` 问题 + 一句普通观察 + 另一个问题),数组让它们**各自独立成条、各带 id**,而不是糊成一段。YAML 的多行 `|` 块对「带换行、带 `#`、带引号」的自由文本最省转义(对照 [card create 的 `@file`/`@-`](../../cli/v4/card.md#文本传文件--stdin) 同理)。

---

## 3. `#…？` → 自动建卡 / 关联老卡

mark 内容里只要冒出一个问题,就用 **`#…？` 语法**就地标:`#` 起头、**到第一个 `？`(或半角 `?`)收尾**,中间就是问题文本。

```
配 pty 的时候用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？他其实想要可重连会话。
                              └──────────── 一个问题 ────────────┘
```

写入这份 mark 时,系统对每条 mark 的 `mark` 文本:

1. **解析**出所有 `#…？` 问题(`#` 起、`？`/`?` 止;一条 mark 里可有多个)——于是「这条 mark 里有几个问题」是**自动数出来的**,不靠 AI 自己报。
2. 每个问题走 [card.md §6](card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question) 的三岔(embed 问题文本 → 撞 `cards` / issue 向量库):
   - **新问题(检索 miss)→ 建一张新卡**(`issue` = 问题文本,还没答案、在等答案)。
   - **老问题(检索 hit)→ 关联**到那张已有卡(**不动老卡任何分数**——相关性只在召回时算,见 [card.md §3](card.md#3-第二推credence--现算的质量分相关性只在召回时算))。
   - 两种情况都**记一条 [`card_sessions`](../../structure/v4/card-session.md)**:`card_id` + `session_id` + **`mark`(那条 mark 的 id,即 `sess_xxx#m1` 里的 `m1`)**,这就是「这个 session 的**这条 mark** 启发 / 碰到了这张卡」的出处(§4)。
3. mark ↔ card 的关联**写进这条 mark 的 `questions[]`**(`card_id` + `is_new`:建了新卡还是关联老卡)——这是 **canonical**(file,§6);SQLite 里的 `card_sessions` 表就是**从这些 `questions[]` 派生出来的可 join 索引**。

**这一步把「判断惊讶」从 AI 手里拿走了**:AI 只管**读 + 自然地 `#…？` 标问题**;「这是不是个新问题(= 惊讶)」由**检索**算(miss = 新卡)。这正是 [card.md §6 命门](card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question) 最自然的落地——**惊讶 grounding 在检索,而不是 AI 自评**。

---

## 4. `card_source` 指向 mark,而不是仅仅 session

这是本次相对旧设计最关键的调整。旧 `card_sessions` 的出处是 `(session_id, indexes)`——只能说「这卡来自这个 session 的第 11–15 轮」,**粒度到 round、且要靠 round index 间接定位**。新设计让出处**直接指那条 mark**——而 mark **不是一等 id,是 session 的附属**,id `m<n>`、寻址 `<session_id>#<id>`,所以 `card_sessions` 里出处 = `session_id` + 那条 mark 的 **id `mark`(`m1`)**:

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "mark": "m1",
  "position_id": "",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「`sess_def456` 里**第 1 条 mark**(`sess_def456#m1`)启发 / 生出了 `card_01jz8k2m`」。

为什么指 mark 更好:

- **出处是「那句感悟」,不是「那几轮原文」**:真正启发建卡的是 AI 写的那条 mark(带 `#…？` 的那句),而不是裸 round 正文。指 mark,出处就**精确到提问的那句话**,点开能看到「当时是怎么想到这个问题的」。
- **round 是 mark 的属性,可派生**:每条 mark 挂在 `(session_id, round_index)` 上,所以**给了 `(session_id, mark)` 就等于给了 round**——不丢信息,反而多了「哪条 mark」这一层。
- **答案出处同样精确**:某条 mark 写出了答案 → 落一个 Position,这条 `card_sessions` 的 `position_id` 指那个答案、`mark` 指写出它的 mark 序号(`position_id=""` 则指向问题/卡本身)。

### `card_sessions` 形态调整(设计)

```sql
-- card ↔ session 出处:哪条 mark(在哪个 session)启发了这张卡/哪个答案;支持多 mark
CREATE TABLE card_sessions (
  card_id     TEXT NOT NULL,             -- 哪张卡
  session_id  TEXT NOT NULL,             -- 哪个 session(扁平,可 join;无 FK)
  mark        TEXT NOT NULL,             -- 哪条 mark 的 id(m1 / m2 …;寻址 = session_id#mark)
  position_id TEXT NOT NULL DEFAULT '',  -- 启发了哪个答案('' = 关联到问题/卡本身)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, session_id, mark, position_id)
);
CREATE INDEX idx_card_sessions_session ON card_sessions(session_id);          -- 反查「这个 session 启发了哪些卡」
CREATE INDEX idx_card_sessions_mark    ON card_sessions(session_id, mark);    -- 反查「这条 mark 启发了哪些卡」
```

- 把旧的 `indexes TEXT`(round 区间)**换成 `mark TEXT`**(mark id `m1`/`m2`)。出处寻址 = `session_id` + `#` + `mark`(如 `sess_def456#m1`)。round 不再冗存——它是 mark 的属性,要时从 mark 文件取。
- PK 加进 `mark`:同一卡可被多条 mark(乃至多 session)启发;同一条 mark 也可同时启发问题 + 答案(不同 `position_id`)。
- `idx_card_sessions_mark`(`session_id, mark`):支持「拿一条 mark(`sess_xxx#m1`),反查它建/连了哪些卡」。

> **与已落地实现的差异**:当前实现的 `card_sessions` 用的是 `(session_id, indexes)`(card.md §8 那版)。本篇把它改成 `(session_id, mark)`,属**未实施的设计调整**,落地时连带 mark 的存储 / 解析一起做。

---

## 5. 多遍 mark ↔ 卡的生命周期

`#…？` 建的卡一开始**只有问题、还没答案**。答案(Position)也从 mark 里长出来:

- **第一遍**:`#为什么 pty 会让用户想到 tmux？` → 建一张**还没答案的卡**,`card_sessions` 记这条 mark 为出处。
- **后面的轮 / 后面的遍**:某条 mark 写出「他其实要的是可重连会话」——这是对那张卡的一个**答案**,落成它底下的一个 **Position**(答案文本内联在 Position 上),`card_sessions` 再记一条(`position_id` = 这个答案、`mark` = 写出它的那条 mark id,如 `m5`)。卡从「只有问题」变成「有候选答案」。
- 再有别的证据 顶/踩 这个 Position(review,evidence 也可来自某条 mark 指的 round),按 `credence`(现算)排序——回到 [card.md §3](card.md#3-第二推credence--现算的质量分相关性只在召回时算)。

所以一条龙都长在「逐 round mark」这个自然动作上:**mark 提问(`#…？`)→ 建卡(只有问题)+ 记 `card_sessions` 出处(指 mark);mark 答它 → Position;证据顶踩 → credence**。

---

## 6. 存储:file-canonical、不进 SQLite

mark 是**大段自由文本**,量不小——所以**和 `rounds.jsonl`(round 正文)一个处理法**:**落文件、不进 SQLite**。**每条 mark 一个文件,文件名就是它的 id `m<n>`**,append-only。

```
sessions/<source>/<sid[0:2]>/<sid>/
  rounds.jsonl              ← v3:round 正文(canonical · append-only)
  marks/
    m1.yaml                 ← 第 1 条 mark(文件名 = id)
    m2.yaml                 ← 第 2 条
    …                       ← 重读续标就接着加 m3、m4…
```

一个 `mN.yaml` = 一条 mark,**用 YAML 存**(跟提交同语种,免转换);`description` 从这次提交带下来,`questions` 是写入时解析 `#…？` + 撞库的结果:

```yaml
description: 在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么
round_index: 37
mark: |
  配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？
  他其实想要可重连会话。
questions:
  - raw: 为什么 pty 会让用户想到 tmux
    card_id: card_01j…
    is_new: true
created_at: 2026-06-16T08:30:00Z
```

> **提交 vs 落盘**:一次提交是**一份 round 级 YAML**(顶层 `description` + `marks: [{id, mark}, …]`,§2);写入时把 `marks` **拆开**——每条按它的 `id` 落成 `marks/<id>.yaml`,把这次提交的 `description` 一并带进每个文件(`round_index` 来自这次提交、`questions` 现解析)。wire 是一份带 `description` 的数组、盘上是一文件一 mark(各自留着 `description`),两边都用 YAML。

规则(照搬 round 正文那套不变性):

- **一条 mark 一个文件**:文件名 = mark id `m<n>`。**写一次就不动**(append-only,跟 `rounds.jsonl` 一样);改主意 = 加新 `m<n>`,不覆盖旧文件。
- **序号单调、session 内唯一**:`m1`→`m2`→… 按 append 顺序,不复用、不跳号。重读续标接着往后加,不另起「遍」的目录(谁先谁后看序号 / `created_at`)。
- **不进 SQLite、也不进向量库**:mark 本身不是检索单元;进 `cards` 向量库的是它 `#…？` 出来的**问题(卡)**,卡走正常 card 写路径落 SQLite。
- **mark ↔ card 的链就写在那条 mark 的 `questions[]` 里**;`card_sessions`(SQLite)是**从这些 `questions[]` 派生**的可 join 索引(`card_id` + `session_id` + `mark` id + `position_id`)。

---

## 7. mark 的寻址:`<session_id>#<id>` —— session 的附属,不是一等 id

mark **不进 id 前缀体系**(没有 `mark_` 前缀、没有 `IdKind.MARK`、不 mint 独立 ULID)。它是 **session 的附属**,靠 session 的 id + `#` + mark id(`m<n>`)寻址:

```
sess_def456#m1    ← sess_def456 的第 1 条 mark(= 第一次标注;盘上 marks/m1.yaml)
sess_def456#m2    ← 第 2 条
```

- **`read sess_def456#m1`**:读时先按 `#` 拆成 `(session_id, mark_id)`——`parse_id` 见到 `card_` / `pos_` / `sess_` 等前缀照旧判型;**额外认 `sess_…#m<n>` 这种带 `#` 分片的形态 → 定位「这个 session 的 mark `m<n>`」**(直接读 `marks/m<n>.yaml`),返回它(`description` 场景 + `mark` 文本 + 所属 round + `questions` + 它建/连了哪些卡)。不需要新前缀,复用 session id + 分片。
- **`card_source` 指 `(session_id, mark)`**(§4):出处从「指 session+round 区间」升级成「指那条 mark」,点开就是「当时怎么想到这个问题的」。
- **review / Position 的 evidence** 仍引 round(`indexes`),但「出处 / 启发」这条线统一指 mark——**启发用 mark(`sess#n`),证据用 round(`indexes`)**,各司其职。

> 为什么不给 mark 独立 id:mark 离开 session 没有意义(它是「读这个 session 的第几条感悟」),天然从属于 session。用 `sess_…#n` 这种**分片寻址**,既能精确点到、又不往全局 id 空间里多塞一类前缀——跟「章节#段落」一个直觉。

---

## 8. 与 v3 / card / explore 的关系

- **card.md**:本篇是 card 写路径的**前端 ergonomics**;「新卡 vs 关联」的判定、卡 / Position / credence 全在 card.md,本篇不重复,只负责「从认真读里**自然冒出** `#…？`」+「出处指 mark」。
- **explore.md**:explore 是**在先验 session 上跑 mark** 的工作台——你在 explore 目录里逐 round 提交 mark,`#…？` 建 / 连卡,产物盖 `explore_id` 戳。mark 就是 explore 里「抽卡」的那个具体动作(v4 版工作台另案,见 cli README)。
- **v3 session / round**:mark 按 `round_index` 指回现成的 `rounds.jsonl`,**不改 round 本身**(round 仍 append-only);mark 是 session 目录下**新增的 `marks/` sidecar**,不动 v3 既有结构、也不进 SQLite。
- **v3 tag**:`#…？` 是**类 tag 的就地标记**,但语义不同——v3 `key=value` tag 是死字符串;`#…？` 写入时被**解析成卡 id**(建 / 连),是活的。

---

## 9. 诚实边界 + 待定

- **核心价值是「以写代读」,不是 mark 本身**:mark 的存在意义首先是**逼 AI 逐轮真读**(防走神),其次才是留痕 + 精确出处。哪怕 mark 写完没人再看,这个 forcing function 已经赚到了。
- **`#…？` 不判惊讶,检索才判**:AI 标 `#…？` 只是「我这觉得有个问题」;到底是不是**新**卡(惊讶)由检索 miss/hit 决定。别让 AI 自己说「这是新发现」。
- **别把走神搬进 mark**:逐 round mark 能防顶层扫读的走神;但若允许「一条 mark 糊一大段多轮」,走神会**搬家**。约束:一份 mark 提交对应**一个 round**;数组里每条 mark 是这一轮里**一个**独立感悟。

**待定**:

- **`？` 分隔**:`#…？`(全角)默认;半角 `?` 也认。若问题文本里本身要带问号,用 `#{…}` 包(行内更稳)留作备选。
- **同一问题的归一化**:`#为什么 pty 会让用户想到 tmux？` 和 `#pty 为啥让人想到 tmux？` 该不该 match 到同一张卡——靠 embed 近重还是更严的判定,本质是 card.md §6「`#` 问题撞到哪张卡」的匹配阈值。
- **`id`(`m<n>`)谁分配**:append-only 下天然单调,**系统按 append 顺序分配下一个 `m<n>`**最稳(提交方不必知道当前计数,提交时 `id` 可省);若提交方自带则校验单调、不允许跳号 / 复用。`m<n>` 在 session 内唯一,直接当文件名(§6)。
- **`pass` 怎么触发**:第二遍是人 / AI 主动发起,还是系统在「新建了 N 张卡后」提示回看?留作 explore 工作流细节。
- **mark 的最小产率**:是否每个 round 都必须有 mark(强制逐轮),还是允许「这轮无话可说」跳过——但要显式记「看过、空 mark」,别和「没看」混。
