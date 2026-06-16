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
- **可标很多遍(v1 → v2 → …)**:同一轮可以被**重复标注**。第二遍带着更多 session 上下文 / 更多已建的卡回头看,**常常冒出第一遍没有的新感悟**——所以 `pass` 字段记第几遍,越后面的标注往往越深。
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
   - **新问题(检索 miss)→ 建一张新卡**(`open` 的卡,在等答案)。
   - **老问题(检索 hit)→ 关联**到那张已有卡(annotation ↔ card 连上,顺便给老卡的 salience 加一点:它又被问起了)。
3. 把 annotation ↔ card 的关联落库(`annotation_questions`),`is_new` 记这条 `#` 是建了新卡还是关联老卡。

**这一步把「判断惊讶」从 AI 手里拿走了**:AI 只管**读 + 自然地标问题**;「这是不是个新问题(= 惊讶)」由**检索**算(miss = 新卡)。这正是 [card.md §6 命门](card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question) 最自然的落地——**惊讶 grounding 在检索,而不是 AI 自评**。于是建卡**非常自然**:你认真读、随手标问题,卡就长出来了。

---

## 4. 多遍标注 ↔ 卡的生命周期

`#问题` 建的卡一开始是 **open**(只有问题、没答案)。答案(Position)也从标注里长出来:

- **第一遍**:`#为什么 pty 会让用户想到 tmux` → 建一张 open 卡。
- **后面的轮 / 后面的遍**:标注里写出「他其实要的是可重连会话」——这是对那张卡的一个**答案**,落成它底下的一个 **Position**(引一个 Claim),卡从 open 变成有候选答案。
- 再有别的证据 顶/踩 这个 Position(review),沉浮排序——回到 [card.md §3](card.md#3-第二推credence--salience校验轴和显著轴是两回事) 的论坛动力学。

所以一条龙都长在「逐 round 标注」这个自然动作上:**标注提问 → 建卡(open);标注/后续答它 → Position;证据顶踩 → 沉浮**。

---

## 5. 存储

沿用 file-canonical:标注是 session 的 sidecar,append-only;SQLite 建索引 + 存 `#` 解析出的卡关联。

```
sessions/<bucket>/<session_id>/annotations.jsonl   ← append-only,一行一条标注(canonical)
```

```json
{"annotation_id": "anno_01j…", "round_index": 37, "pass": 2,
 "text": "…#为什么 pty 会让用户想到 tmux…",
 "questions": [{"raw": "为什么 pty 会让用户想到 tmux", "card_id": "card_01j…", "is_new": true}],
 "created_at": "2026-06-15T08:30:00Z"}
```

```sql
CREATE TABLE annotations (
  annotation_id TEXT PRIMARY KEY,            -- anno_<ulid>
  session_id    TEXT NOT NULL,
  round_index   INTEGER NOT NULL,
  pass          INTEGER NOT NULL DEFAULT 1,  -- 第几遍标这一轮(v1/v2/…)
  text          TEXT NOT NULL,               -- 派生副本;canonical 在 annotations.jsonl
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_anno_round ON annotations(session_id, round_index, pass);
-- 标注里 # 出来的问题 ↔ 卡(新建 or 关联)
CREATE TABLE annotation_questions (
  annotation_id TEXT NOT NULL,
  card_id       TEXT NOT NULL,               -- 解析 # 后 match/create 的卡(card.md §6)
  raw           TEXT NOT NULL,               -- 原始问题文本
  is_new        INTEGER NOT NULL,            -- 1 = 建了新卡;0 = 关联老卡
  PRIMARY KEY (annotation_id, card_id)
);
CREATE INDEX idx_anno_q_card ON annotation_questions(card_id);
```

- **annotation 不进向量库**——它本身不是检索单元;进 `cards` 向量库的是它 `#` 出来的**问题(卡)**。
- **多遍 = 多行**(同 `(session_id, round_index)` 不同 `pass`),append-only,从不覆盖。

---

## 6. 与 v3 / card / explore 的关系

- **card.md**:本篇是 card 写路径的**前端 ergonomics**;「新卡 vs 关联」的判定、卡 / Position / 沉浮全在 card.md,本篇不重复,只负责「从认真读里**自然冒出** `#问题`」。
- **explore.md**:explore 是**在先验 session 上跑标注**的工作台——你在 explore 目录里逐 round 标注先验会话,`#问题` 建 / 连卡,产物盖 `explore_id` 戳。annotation 就是 explore 里「抽卡」的那个具体动作。
- **v3 session / round**:annotation 挂在现成的 `session.rounds[index]` 上,**不改 round 本身**(round 仍 append-only);annotation 是**新增 sidecar**,不动 v3 既有结构。
- **v3 tag**:`#问题` 是**类 tag 的就地标记**,但语义不同——v3 `key=value` tag 是死字符串;`#问题` 写入时被**解析成卡 id**(建 / 连),是活的。

---

## 7. 诚实边界 + 待定

- **核心价值是「以写代读」,不是标注本身**:annotation 的存在意义首先是**逼 AI 逐轮真读**(防走神),其次才是留痕。哪怕标注写完没人再看,这个 forcing function 已经赚到了。
- **`#` 不判惊讶,检索才判**:AI 标 `#问题` 只是「我这觉得有个问题」;到底是不是**新**卡(惊讶)由检索 miss/hit 决定(card.md §6 命门)。别让 AI 自己说「这是新发现」。
- **别把走神搬到标注里**:逐 round 标注能防顶层扫读的走神;但若允许「一条标注糊一大段多轮」,走神会**搬家**。约束:一条 annotation 对应**一个 round**。

**待定**:

- **`#问题` 分隔符**:`#…` 到行尾(贴合本例)还是 `#{…}` 包起来(行内更稳)。初稿:行尾默认 + `#{…}` 行内。
- **同一问题的归一化**:`#为什么 pty 会让用户想到 tmux` 和 `#pty 为啥让人想到 tmux` 该不该 match 到同一张卡——靠 embed 近重还是更严的判定,跟 card.md §12 的 Claim 去重同源。
- **`pass` 怎么触发**:第二遍标注是人 / AI 主动发起,还是系统在「新建了 N 张卡后」提示回看?留作 explore 工作流细节。
- **标注的最小产率**:是否每个 round 都必须有标注(强制逐轮),还是允许「这轮无话可说」跳过——但要显式记「看过、无标注」,别和「没看」混。
