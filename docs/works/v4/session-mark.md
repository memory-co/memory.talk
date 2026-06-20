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
last_index: 41          # 乐观锁:提交时我读到的 session 最新 round index
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
- **`last_index` = 乐观锁 + 「当时 session 到哪了」**:提交时填**我读到的 session 最新 round index**。写入时系统拿它跟 session 当前最新 round index 比——**一致才放行**;**不一致 = 标注过程中又来了新 round**(session 还在被 sync 写),你这份是**基于旧视图**的,**拒绝提交**(让你带着新 round 重读再标)。同时 `last_index` 落进 `session_marks` 表(§6),事后能看出**每条 mark 是在 session 长到第几轮时标的**——「当时是个什么情况」。
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

## 4. mark 建的是 **card→session** 出处(`mark` 必选);position→session 的 `mark` 可选

**两条出处链路要分清**(别混成一张表):

| 链路 | mark 颗粒度 | 谁建的 | 表 |
|---|---|---|---|
| **card → session** | **必选**(要支撑 `#…？` 双向关联) | 某条 mark 的 `#…？` 建 / 连了这张卡 | `card_sessions(card_id, session_id, **mark**)` |
| **position → session** | **可选**(主出处是 `indexes`) | `card position --source <sid>:<idx>` 给答案标来源 | `position_sessions(position_id, session_id, **indexes**, mark?)` |

mark 写路径**只产 card→session**:`#…？` miss 建新卡 / hit 连老卡,各记一条 `card_sessions`,出处就是**那条 mark**。**同一 card↔session 可以有多条**——不同 mark(不同感悟)各碰到 / 建了这张卡,各记一条:

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "mark": "m1",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「`sess_def456` 的**第 1 条 mark**(`sess_def456#m1`)的 `#…？` 建 / 连了 `card_01jz8k2m`」。**没有 `position_id`**——这是卡级关系。

**为什么两条链路 mark 颗粒度不同**:
- **card→session 必选 mark**——卡是 mark 里 `#…？` **建/连**出来的,要支撑 `#…？` 的**双向关联**(card↔mark 互查),所以非到 mark 不可。
- **position→session 可选 mark**——Position(答案)**本身就是「观点」主体**,它的主出处是「从哪几轮长出来的」(round `indexes`);到底是不是某条 mark 触发的可以**顺手记一下(可选)**,但不强求——再硬挂一条 mark 容易跟「答案本身这个观点」重复。所以答案出处走 [`position_sessions`](../../structure/v4/position-session.md):`indexes` 必填、`mark` 选填。

### `card_sessions` 形态(设计)

```sql
-- card → session 出处:哪条 mark 建/连了这张卡;同一 card↔session 可多条(不同 mark)
CREATE TABLE card_sessions (
  card_id     TEXT NOT NULL,   -- 哪张卡
  session_id  TEXT NOT NULL,   -- 哪个 session(扁平,可 join;无 FK)
  mark        TEXT NOT NULL,   -- 哪条 mark 的 id(m1 / m2 …;寻址 = session_id#mark)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, session_id, mark)
);
CREATE INDEX idx_card_sessions_session ON card_sessions(session_id);
CREATE INDEX idx_card_sessions_mark    ON card_sessions(session_id, mark);
```

- 旧设计的 `(session_id, indexes)` + `position_id` 一张表**拆成两条链路**:卡级 → `card_sessions`(`mark` 必选,本表);答案级 → [`position_sessions`](../../structure/v4/position-session.md)(`indexes` 必选 + `mark` 可选)。
- **PK `(card_id, session_id, mark)`、无 `position_id`**:同一卡可被同一 session 的**多条不同 mark** 建 / 连。

> **与已落地实现的差异**:当前实现 `card_sessions` 是 `(card_id, session_id, position_id, indexes)` 一张表(card.md §8 那版,卡级 + 答案级混在一起)。本篇把它拆成 `card_sessions`(mark)+ `position_sessions`(indexes),属**未实施的设计调整**。

---

## 5. mark 建问题,答案 / 表态各走各的

`#…？` 建 / 连的是**卡(问题)**,一开始**只有问题、还没答案**。三条线分开,别都塞进 mark:

| 动作 | 命令 / 入口 | 落哪 | 出处 |
|---|---|---|---|
| **提问 → 建/连卡** | `session mark` 里的 `#…？` | 卡 + `card_sessions` | **mark**(`sess#m<n>`) |
| **给问题加答案** | [`card position --claim … --source <sid>:<idx>`](../../cli/v4/card.md#card-position) | Position + [`position_sessions`](../../structure/v4/position-session.md) | **round `indexes`**(mark 可选) |
| **对答案顶/踩** | [`card review --argument … --cite <sid>:<idx>`](../../cli/v4/card.md#card-review) | `reviews` | **round `indexes`**(证据) |

- **提问**:某条 mark 的 `#…？` miss → 建新卡(只有问题)/ hit → 连老卡;记 `card_sessions`(出处 = 那条 mark)。
- **答它**:`card position` 给这张卡加一个 **Position**(答案文本内联),它的出处 = `position_sessions`(那个答案从哪几轮长出来,`indexes` 必填;`mark` 可选,见 §4)。
- **评它**:`card review` 顶/踩某 Position,`argument` 累成计数,按 `credence`(现算)排序——回到 [card.md §3](card.md#3-第二推credence--现算的质量分相关性只在召回时算)。

> mark 写路径**只负责把问题从认真读里捞出来**(`#…？` → 卡);答案和表态是后续显式动作,各有各的出处链路。这正是「启发用 mark、出处用 indexes、证据用 indexes」三线分工。

所以一条龙都长在「逐 round mark」这个自然动作上:**mark 提问(`#…？`)→ 建卡(只有问题)+ 记 `card_sessions` 出处(指 mark);mark 答它 → Position;证据顶踩 → credence**。

---

## 6. 存储:mark 文件(canonical)+ `session_marks`(SQLite 派生索引)

跟 session 一个分法:**正文落文件、元信息进表**。mark 正文(`mark` 大段文本)**落 YAML 文件**(canonical,像 `rounds.jsonl`);mark 的**元信息**(序号 / round / `last_index` / 时间)进 **`session_marks` 表**(SQLite 派生索引,像 `sessions` 表),用来撑乐观锁、寻址、反查。

### 文件(canonical):一条 mark 一个 `m<n>.yaml`

**每条 mark 一个文件,文件名就是它的 id `m<n>`**,append-only:

```
sessions/<source>/<sid[0:2]>/<sid>/
  rounds.jsonl              ← v3:round 正文(canonical · append-only)
  marks/
    m1.yaml                 ← 第 1 条 mark(文件名 = id)
    m2.yaml                 ← 第 2 条
    …                       ← 重读续标就接着加 m3、m4…
```

一个 `mN.yaml` = 一条 mark,**用 YAML 存**(跟提交同语种,免转换);`description` / `last_index` 从这次提交带下来,`questions` 是写入时解析 `#…？` + 撞库的结果:

```yaml
last_index: 41
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

> **提交 vs 落盘**:一次提交是**一份 round 级 YAML**(顶层 `last_index` + `description` + `marks: [{id, mark}, …]`,§2);写入时把 `marks` **拆开**——每条按它的 `id` 落成 `marks/<id>.yaml`,把这次提交的 `last_index` / `description` 一并带进每个文件(`round_index` 来自这次提交、`questions` 现解析)。wire 是一份带头信息的数组、盘上是一文件一 mark,两边都用 YAML。

### 表(派生索引):`session_marks`

```sql
-- mark 元信息(派生自 marks/*.yaml);撑乐观锁 + 寻址 + 反查。mark 正文不进表(留 YAML)
CREATE TABLE session_marks (
  session_id  TEXT NOT NULL,        -- 哪个 session
  mark        TEXT NOT NULL,        -- mark id(m1 / m2 …);寻址 = session_id#mark
  round_index INTEGER NOT NULL,     -- 标的是哪一轮
  last_index  INTEGER NOT NULL,     -- 标这条 mark 时 session 的最新 round index(乐观锁基线 + 当时情况)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (session_id, mark)
);
CREATE INDEX idx_session_marks_session ON session_marks(session_id);  -- 列一个 session 的所有 mark / 取最大序号
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空;canonical 是 `marks/*.yaml`,表丢了能从文件重建)。
- `mark` 正文**不进表**(大文本留 YAML);表只放**能 join / 能比 / 能排**的元信息。
- 取「session 下一个 mark 序号」「session 当前 `last_index` 基线」「某条 mark 标在第几轮」都走这张表,不必扫文件。

### 乐观锁:`last_index` 怎么校验

提交一份 mark 时,系统:

1. 读 session 当前**最新 round index**(`max(round_index)`,来自 sessions/rounds)。
2. 跟提交里的 `last_index` 比:
   - **相等** → 放行:`marks/m<n>.yaml` 落盘 + `session_marks` 各插一行。
   - **不等**(session 又长了新 round)→ **拒绝**(409 / conflict):你这份是基于旧视图标的,带着新 round **重读再标**。
3. 同一 session 并发两份提交,只有 `last_index` 仍等于当前的那份能进;另一份因序号 / 基线已变而被挡——**乐观锁,不上行锁**。

### 不变性(照搬 round 正文那套)

- **一条 mark 一个文件,写一次就不动**(append-only);改主意 = 加新 `m<n>`,不覆盖旧文件 / 旧表行。
- **序号单调、session 内唯一**:`m1`→`m2`→…,不复用、不跳号;重读续标接着往后加。
- **mark 不进向量库**:进 `cards` 向量库的是它 `#…？` 出来的**问题(卡)**,卡走正常 card 写路径。
- **mark ↔ card 的链写在那条 mark 的 `questions[]` 里**(canonical · YAML);[`card_sessions`](../../structure/v4/card-session.md) 是从这些 `questions[]` 派生的 card↔session 可 join 索引(`card_id` + `session_id` + `mark` id + `position_id`)。**`session_marks` 管 mark 自己的元信息,`card_sessions` 管 mark→card 的出处边**,两张表各司其职。

---

## 7. mark 的寻址:`<session_id>#<id>` —— session 的附属,不是一等 id

mark **不进 id 前缀体系**(没有 `mark_` 前缀、没有 `IdKind.MARK`、不 mint 独立 ULID)。它是 **session 的附属**,靠 session 的 id + `#` + mark id(`m<n>`)寻址:

```
sess_def456#m1    ← sess_def456 的第 1 条 mark(= 第一次标注;盘上 marks/m1.yaml)
sess_def456#m2    ← 第 2 条
```

- **`read sess_def456#m1`**:读时先按 `#` 拆成 `(session_id, mark_id)`——`parse_id` 见到 `card_` / `pos_` / `sess_` 等前缀照旧判型;**额外认 `sess_…#m<n>` 这种带 `#` 分片的形态 → 定位「这个 session 的 mark `m<n>`」**(直接读 `marks/m<n>.yaml`),返回它(`description` 场景 + `last_index`〔标它时 session 到第几轮〕 + `mark` 文本 + 所属 round + `questions` + 它建/连了哪些卡)。不需要新前缀,复用 session id + 分片。
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
