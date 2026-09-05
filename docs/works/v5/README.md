# memory.talk v5 —— 总设计(定位 + 三层抽象)

> **状态:定位稿,未实施。** 这篇只回答三件事:memory.talk 是什么、它由哪几层抽象组成、这几层怎么咬合。字段、表、命令、端点一概不在这里——那些等定位敲定后再分篇立(同 [v4](../v4/README.md) 的 works / cli / api / structure 四目录分工)。
>
> 分篇:[task.md](task.md)(做事层:task 树)、[issue.md](issue.md)(议事层:树上节点管、派活取证)、[card.md](card.md)(记事层:维基式事实条目,issue 是它的讨论页)。
>
> 读法:先 §1 看定位怎么变,再 §2 看三层各是什么,§3 看它们之间的循环。§4 是跟 v3 / v4 / shellbase 的继承关系,§5 是留待后续分篇敲定的问题。

---

## 1. 重新定位:从「记忆库」到「工作台」

### 1.1 v1–v4 的定位:会话的事后记忆

到 v4 为止,memory.talk 一直是一个**挂在别人工作旁边的记忆库**:

```
Claude Code / Codex 在别处工作  →  sync 把会话抄进来  →  抽卡  →  下次开会话时 recall 注入
```

它的主语是「会话」:会话在外面发生,memory.talk 事后导入、事后提炼、事后召回。这条线的每一版都在打磨「卡」这一个对象——v3 是陈述卡 + 论坛动力学,v4 把卡升级成「问题 + 竞争答案」的被治理问题图。但**工作本身**始终不在 memory.talk 里,它只看得到工作留下的对话记录。

### 1.2 v5 的定位:像 Codex work 一样的工作台,记忆是它的副产物

v5 把主语换掉:**memory.talk 是一个工作台,工作在它里面发生**。定位对标 OpenAI Codex app 的那套形态——agent 在按项目组织的线程里跑,你在多个任务之间切换而不丢上下文,任务可以并行、可以被看、可以被接管([Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/))。

差别在于 memory.talk 多出「记忆」这一半:Codex work 的任务做完就是做完了,memory.talk 的任务做完会**长出问题和认知**,并在下一个任务里被想起来。一句话:

> **memory.talk v5 = 一个跑 code agent 的工作台,它把「做事」「议事」「记事」三层接成一个闭环。**

这三层就是 v5 的三个抽象:**task、issue、card**。

---

## 2. 三层抽象:task / issue / card

| 层 | 对象 | 它是什么 | 主语在干什么 | 来源 |
|---|---|---|---|---|
| 做事 | **task** | 一个工作单元,里面盛放若干个 **code agent session**;复杂的事是一棵 **task 树** | 干活 | 在 memory.talk 里**原生实现**,底层逻辑与 [shellbase](https://github.com/memory-co/shellbase) 完全一致 |
| 议事 | **issue** | 一个问题 + 围绕它的立场与论证(IBIS) | 讨论、争辩、定夺 | v4 的问题图(issue / position / argument) |
| 记事 | **card** | 维基式的事实条目:一条**争完了、可以直接查**的事实 | 记住、被想起 | v4 卡去掉争的部分后剩下的陈述 + 召回单元 |

三层的分工一句话:**task 装已经定下来、正在做的事;issue 装还没定的事;card 装已经站住、可以带走的认知。** 三层里只有 task 有状态和完成——它是过程,做完就结束(复杂的事是一棵树,叶子先完、往上收拢);issue 是过程里冒出来、可以跨 task 一直开着的争论;card 是争论沉淀下来的、能被反复召回的结论。

### 2.1 task:盛放 code agent session 的工作单元

task 是 v5 的顶层对象,**取代 session 成为 memory.talk 的入口**。一个 task 就是 shellbase 里那个 window 的原生版本:一块可分割的画布,每个块由一个虚拟 URI 定位(`claude:///workspace/proj`、`codex:///workspace/proj`、`bash://`、`file://`、`https://`),块背后是 tmux 里活着的一个进程,断线重入现场无损。

- **task 里的每个 agent 块 = 一个 code agent session**。shellbase 那套「块即 URI、后端是状态唯一权威、无中生有 + 重入」的底层逻辑在 memory.talk 里**原生实现、完全一致**;shellbase 作为独立项目到此为止,memory.talk 不重新发明 agent 运行时,只是把这个运行时收进自己家。
- **session 从「事后导入的对象」变成「在 task 里原生发生的对象」**。v3 的 sync(从平台目录抄会话)退成兼容路径——task 里跑的 session,memory.talk 本来就看得见。
- **task 承接 v3/v4 的 explore**。explore 原本是「一个目录 + 一条时间分割线」的抽卡工作区;v5 里每个 task 天然就是这样一个工作区:task 里的 session 是它的先验素材,之后的 task 是它的后验证据。explore 不再单独存在。
- **复杂的事是一棵 task 树**。task 可以有子 task:根是「把 X 做出来」,叶子是真正坐下来干的一件小事。拆分、顺序、状态、完成——执行的结构全部落在 task 上;树上每个节点都可以有自己的画布。
- task 有目标、有状态、有始终、有父子、有归属的项目(工作目录),但 task 不做认知——它只负责让工作发生并把过程留下来。

### 2.2 issue:IBIS 结构的议事层

issue 是「一个问题」,以及围绕它的 **position(立场 / 候选答案)** 和 **argument(支持 / 反对的论证)**。这就是 IBIS(Issue-Based Information System)那套本体,v4 已经把它推导出来了([v4 card.md §4](../v4/card.md));v5 把它从「卡」里独立出来,成为 task 和 card 之间的一层。

- **issue 从 task 里冒出来**。做事过程中的每个「为什么」「该不该」「哪个更好」都是一个 issue;v4 设计的逐 round 标注 + `#问题` 自动建问题([session-annotation.md](../v4/session-annotation.md))就是 issue 的主要入口。
- **issue 是跨 task 的,但有人管**。一个问题可以在 task A 里提出、在 task B 里得到新立场、在 task C 里被反驳;每个 issue 由 task 树上一个节点(manager)负责推,推不动时可以派出新 task 去取证。issue 之间用 IBIS 的边连成图(细化、引出、质疑、取代)。
- **issue 不需要「关闭」**。IBIS 允许多个 position 长期竞争,哪个当下占优靠论证的多寡(v4 的 credence 现算)决定,不钉成已解决状态。
- issue 的作用是**把争论结构化地留住**——它是可讨论的对象,但不是召回的单元。召回的单元是 card。

### 2.3 card:本地论的认知卡片

card 是记事层:**一条事实,像维基百科的一个词条**。一个事实一张卡,讲清楚、能独立读懂、事实自带语境(关于哪个项目、哪个用户、哪个场景——这是「本地论」在卡上的落法,不是单独的治理字段)。卡上**没有**顶踩、可信度、沉浮、竞争候选、状态位——v3 的论坛动力学和 v4 的 credence 在 card 里全部不用。

- **issue 是 card 的讨论页**。还在争的待在 issue,争完的写成 card;没什么可争的事实也可以直接写卡,后来有人不同意再开 issue 挂上去。
- **card 可以改,历史留着**。事实变了就改卡,像编辑词条;被推翻就废弃。没有沉浮,一张卡不会自己掉下去,它的每次变化都是明确的编辑动作。
- **card 是召回单元**。新 task 开始或 agent 思考时查词条——只按相关性排,没有第二个排序轴;注入正文和链接,agent 不够用就顺链接去看讨论页和出处。
- **不同意就去讨论页**。用卡的结果不回写到卡上,而是回到它的 issue 加立场、加论证,议出结果再改卡。

---

## 3. 三层怎么咬合:一个闭环

```
            做事                      议事                       记事
   ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
   │      task        │      │      issue       │      │      card        │
   │  code agent      │ 标注  │  问题            │ 结晶  │  本地论认知卡    │
   │  session × N     │─────▶│  + position × N  │─────▶│  答案 + 适用范围  │
   │  (原生画布)       │ #问题 │  + argument      │      │  (召回单元)       │
   └──────────────────┘      └──────────────────┘      └──────────────────┘
            ▲                         ▲                          │
            │                         │ 后验 task 回流论证          │
            │                         └──────────────────────────┤
            │                              recall:新 task 开工时注入   │
            └──────────────────────────────────────────────────────┘
```

顺着走一遍:

1. **task 里干活**:若干 agent session 在 task 的画布上跑,过程按 round 留下。
2. **task → issue**:对 session 逐 round 标注(以写代读),标注里 `#` 出来的问题经检索判定——新问题建 issue,老问题挂到既有 issue;标注里给出的回答落成 position,后续证据落成 argument。
3. **issue → card**:争出结果的 issue 写成 / 改一张 card;没什么可争的事实直接写卡。
4. **card → task**:下一个 task 开工,recall 拿语境撞 card,把命中的卡注入 agent 的上下文。
5. **task → issue(回流)**:新 task 里发生的事,对老 issue 的 position 构成新的支持或反对——这就是 explore 想做的「后验验证」,在 v5 里是每个 task 天然具备的能力。

三条守住闭环不退化的原则,全部继承自 v4,这里只点名不展开:

- **沉默 ≠ 确认**:一个 task 没提到某个 issue,不给它任何分。
- **惊讶 grounding 在检索**:「这是不是新问题」由检索 miss 判定,不由 agent 自评。
- **「不该用」≠「错」**:卡的适用范围和卡的对错是两件独立的事。

---

## 4. 继承什么、换掉什么

| | 来源 | v5 怎么处理 |
|---|---|---|
| 画布 / 块即 URI / 终端 attach / window 状态 | shellbase v1 | **在 memory.talk 里原生实现,底层逻辑完全一致**;shellbase 不再作为独立项目继续,它的设计文档是 task 运行时的蓝本 |
| session / round(append-only)、file-canonical、searchbase、migration 框架 | v3 | 沿用不动,只是 session 的上游从 sync 变成 task |
| explore(先验 / 后验工作区) | v3 设计 | **并入 task**,不再独立 |
| insight(v3 的陈述卡) | v3 → v4 改名 | 继续只读可搜,慢慢下掉,不变 |
| 问题图(issue / position / argument、IBIS 边、credence 现算) | v4 card | 成为 **issue 层**;机制不变,名字归位 |
| 位(scope)/ 变(append-only + fork) | v4 card 治理 | 位不再是字段,事实陈述自带语境;变不再适用于 card——卡是可编辑 + 有历史的词条(issue 里的立场仍只增不改) |
| 逐 round 标注 + `#问题` | v4 session-annotation | 成为 task → issue 的主入口 |
| 召回(撞问题 + 答案、credence 排序、scope 随注入) | v4 读路径 | 召回单元改成 card,**只按相关性排**,credence 那一轴去掉(对立候选还在 issue 里,不进卡) |

一句话概括 v5 相对 v4 的改动:**往上加了 task 这一层把工作装进来,往下把 v4 的 card 拆成 issue(争论)和 card(维基式事实条目),card 上不再有任何沉浮。**

---

## 5. 定位层面还没敲死的事

这些都会各自分篇,本稿只列出来,不在这里定:

- **issue 与 card 的边界**:[card.md §2](card.md) 定为词条 / 讨论页——还在争的待 issue,争完的写卡;写卡是编辑动作,不是阈值触发。
- **task 的边界**:一个 task = 一个 window(画布),还是一个 window 里可以有多个 task。这取决于「工作单元」和「屏幕布局」要不要绑死。
- **task 的结束语义**:task 做完之后 session 是否冻结、标注是否还能追加、后验回流从哪一刻开始算。
- **多平台**:task 里的 agent session 目前只考虑 tmux 里跑的 CLI agent(claude / codex);外部平台(网页版 Codex、别的机器)的会话是否还走 sync 兼容路径进 task。
- **命名**:「本地论」这个提法在文档里怎么落——目前落成「事实陈述自带语境」([card.md §3](card.md)),不单立字段。
