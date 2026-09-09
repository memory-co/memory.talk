# issue —— 有人管、能派活的问题(v5 设计)

> **状态:框架稿,未实施。** 本篇只立 issue 这一层的大框架:它是什么、从哪冒出来、谁管它、论证要干活时怎么派 work、争完之后怎么写成 card。IBIS 节点与边的机制在 v4 已推导清楚,这里只点名不重复;字段 / 端点 / 命令后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 总设计(work / issue / card 三层): [README.md](README.md)
- v5 work 树(issue 的原料来源、管理者所在、派活的去处): [work.md](work.md)
- v5 collect(issue 在认知层里是一个 layer:`layer/issue`;对象是任意位置的 `<名>.issue/` 目录): [collect.md](collect.md)
- v5 manager(issue 目录下的 `manager.json` 决定谁管它、变动打给谁): [manager.md](manager.md)
- v4 问题图(issue / position / argument、IBIS 边、credence 现算——本篇机制的来源): [../v4/card.md](../v4/card.md)
- v4 逐 round 标注 + `#问题`(issue 的主入口): [../v4/session-annotation.md](../v4/session-annotation.md)

---

## 1. 一句话:issue 是「一个问题,加上围绕它的立场和论证」

做事的时候会不断冒出问题:为什么这样、该不该那样、A 和 B 选哪个。issue 就是把**一个问题**留住,底下挂上**几个立场**(position,候选答案),每个立场再挂上**论证**(argument,带证据的支持或反对)。这套三节点结构就是 IBIS,v4 已经从卡的需求里把它推导出来了([v4 card.md §2–§4](../v4/card.md));v5 把它从「卡」里独立出来,成为 work 和 card 之间的**议事层**。

issue 跟另外两层的分工很清楚:work 是**做**,card 是**记**,issue 是**议**——问题在这里被摆出来、被争、被验,直到某个立场站得住,再写成 card。换个说法:**work 装已经定下来、正在做的事,issue 装还没定的事**([work.md §2](work.md))。一件复杂的事怎么推进,看 work 树;推进中哪些地方还没定,看树上各节点管的 issue。

---

## 2. issue 从哪来:从 work 的痕迹里冒出来

issue 的主入口是 work 留下的痕迹。对一个 work 的 session 逐 round 标注(以写代读),标注里 `#` 出来的问题拿去检索:

- **检索没着落** → 这是个新问题,建一个 issue。
- **检索撞上老问题** → 挂到那个 issue 上;标注里如果给出了回答,落成它的一个立场;如果是对现有立场的证据,落成一条论证。

「是不是新问题」由检索判定,不由 agent 自评——这是 v4 的命门,v5 原样继承。除此之外 issue 也可以**直接手建**:人在 work 里意识到一个问题,不必等标注,直接提。

每个 issue 都记得**它从哪个 work 的哪些 round 冒出来**。这是出处,不是归属——冒出它的 work 做完了、冻结了,issue 还活着。

---

## 3. issue 有人管:目录下的 manager.json

v4 的问题图有一个没解决的问题:**一个问题被提出来之后,谁在推它**?卡建了、立场挂了,然后就等着后续对话碰巧撞上它。没人负责去找答案、去安排验证。

v5 用 [manager.md](manager.md) 的机制给每个 issue 一个 **manager work**——work 树上管这个问题的那个节点。绑法就是在 issue 的目录下放一个 `manager.json`:

```
memory.talk/配置/该走文件还是环境变量.issue/
├── issue.json          ← 问题、立场、论证、边
└── manager.json        ← {"work": "work_…"}:谁管它
```

issue 是一个带 `.issue/` 后缀的目录,放在它相关的东西旁边——同一个文件夹里可能还有它引用的原文(origin)和它争出来的卡(`.card/`)。

- **manager 就是树上正卡在这个问题上的 work**。做「把 X 做出来」这件事时冒出「数据库该不该换」,那 X 这个节点(或它下面正做到这一步的那个子节点)就是这个 issue 的 manager。不必为了管一个问题专门开 work——问题是在做事时冒出来的,管它的就是正在做那件事的节点。
- **issue 的每一次变动都打到 manager work 的收件箱**:新立场、新论证、新的边、被写成了卡——manager work 里的 agent 看到变动,决定下一步(派活取证、写卡、换绑)。这是「有人管」的实际含义:**不是名单上有个名字,是变动会到它手里**。
- **manager work 是议这个问题的现场**。在它的画布里开 agent 会话去梳理立场、找资料、判断现有论证够不够、决定下一步要验什么。这个 work 的 session 痕迹就是这个 issue 的**议事记录**。
- **manager work 是普通 work**。它跟别的 work 一样有画布、有成员、有状态、有父子;唯一多出来的是变动先到它这里。它没有更大的权限([member.md](member.md):不做权限)。
- **一个 issue 同一时间只有一个 manager**(最近的那个 `manager.json`);**一个 work 可以管多个 issue**。
- **可以继承、可以换、可以没有**。issue 自己目录下没有 `manager.json`,就往上找——所在主题文件夹的 `manager.json`(它管这个文件夹里所有层的东西,不只 issue),再往上是 Collect 根上的兜底;所以「一个 work 管这个主题下所有还没人专门管的问题」只要在那个文件夹里放一个文件。换绑 = 改这个文件(一次 `[issue]` 提交,`git log manager.json` 就是换绑史);一路都找不到 = **没人管的问题**,这是有用的状态——issue 列表里一眼看出哪些在推、哪些搁着。

> 出处 work 和 manager work 是两回事:前者是**冒出**这个问题的地方(可能是在做别的事时顺手撞见的),后者是**推进**这个问题的地方。它们常常是同一个节点;不是的时候,通常是「在叶子上撞见、但该由父节点来管」——比如做功能 A 的某一步时发现「数据库该不该换」,这个问题比 A 大,该挂到 A 的父节点去管。

---

## 4. 论证要干活:从 issue 派出新 work

一个立场站不站得住,常常不是想出来的,是**做出来的**:跑一次基准、把另一种方案原型一遍、去把那份文档读完。这些活不该在 manager work 里顺手做——那会把「议」和「做」搅在一起,议事记录里全是跑测试的输出。

所以 v5 允许**从 issue 派出 work 去取证**:

- 在 manager work 里判断「要验这个立场,得去做 X」→ **为这条论证开一个新 work**,挂在 manager 下面当子节点。这个 work 跟任何 work 一样干活:开 agent 会话、跑、看结果。
- 这个 work 记得自己是**为哪个 issue 的哪个立场**开的,所以它的结果有地方落——做完后,它的痕迹成为那个立场的一条**论证**(支持、反对或中立,证据就是这个 work 里的那些 round)。
- 派出去的 work 做完就是做完了。它挂在 manager work 下面,所以「做完」这个变动沿 work 树的隐式 manager 链([manager.md §3](manager.md))打回 manager work 的收件箱;manager 看它的 rounds,把结果记成那个立场的一条**论证**——这一步也是一个 `[issue]` 提交,又打回 manager 自己(自己造成的,不投递)。然后接着议。

这样 work 和 issue 之间就是**双向的**:work 里冒出 issue,issue 又派出 work。三种 work 角色摆在一起:

| work 的角色 | 跟 issue 的关系 | 它留下什么 |
|---|---|---|
| **出处 work** | issue 从它的痕迹里冒出来 | 问题本身(以及可能的第一个立场) |
| **manager work** | 绑定给 issue,负责推它 | 议事记录:梳理、判断、派活 |
| **论证 work** | 为某个立场的取证而开 | 一条带证据的论证 |

三种角色**不是三种 work**——work 只有一种,只是它跟 issue 的关系不同。一个 work 完全可以同时是某个 issue 的出处、另一个 issue 的 manager、第三个 issue 的论证来源。

还有一条反向的路:**issue 的胜出立场变成 work**。「这件事怎么拆」「选哪条路」这类问题议出结果后,那个立场直接落成 work 树上的新节点——一个决定,就是一个 issue 的胜出立场被转成了树上的节点([work.md §2](work.md))。这跟论证 work 不同:论证 work 是**为了验**一个立场而开的,胜出立场转成的 work 是**照着**一个立场去做。

---

## 5. 立场怎么竞争、issue 为什么不关闭

沿用 v4,只点名:

- **立场之间靠论证竞争**。每个立场的支持 / 反对论证累成计数,排序时现算一个可信度(credence);哪个立场当下占优,看它。
- **issue 不设「已解决」**。IBIS 允许多个立场长期并存;哪个立场当下占优看可信度,不钉成状态。争出结果不是关闭 issue,而是把结果写成 card(§7)。一个没有任何立场的 issue 也合法——它就是个还在等答案的问题。
- **立场只增不改**。改主意是加一个新立场、让论证把旧的压下去,不是改旧立场。
- **沉默不算数**。一个 work 没碰到这个 issue,不给任何立场加分减分。

manager work 的存在不改变这些规则——它不能「拍板」把一个立场钉成正确;它能做的是**派活取证**,让论证多起来,让竞争有结果。

---

## 6. issue 之间连成图

issue 不是孤立的,它们之间用 IBIS 的边连着:一个问题是另一个的细化、一个立场引出了新问题、一个问题质疑另一个的前提、一个问题重述并取代了另一个。边的类型学 v4 已定([v4 card.md §4](../v4/card.md)),v5 原样继承,只是节点从「卡」改叫 issue。

issue 图和 work 树是**两套层级,各管各的**:work 树表达「事怎么拆」,issue 图表达「问题怎么细化」。它们通过 manager 绑定对上——一个大问题细化出的几个小 issue,可以绑到同一个节点、也可以各自绑到它的子节点上,看问题落在哪一步。不要用 issue 图的「细化」边代替 work 的父子(事的拆分有状态和完成,问题的细化没有),也不要用 work 树代替 issue 图(问题之间的关系不只有细化)。

---

## 7. issue → card:争完的写成词条,issue 是它的讨论页

issue 和 card 的关系就是维基的讨论页和正文(见 [card.md §2](card.md)):争在 issue 里争,争出结果——某个立场站住了——就把它**写成一张 card**(或者改一张已有的卡)。card 上没有立场、没有计数,只有事实;card 链接回它的 issue,顺着能一路挖回 manager work 的议事记录和论证 work 的证据。

在 Collect 里这是**两个相邻的提交,各在自己的 layer**([collect.md §5](collect.md)):`[issue] decide iss_…#p2 -> card …`(issue 记下「这个立场写成了卡」)+ `[card] write …`(卡的正文),带同一个 `Decision:` trailer。issue 在下、card 在上——写卡、改卡的提交碰不到任何 `.issue/` 目录里的文件,hook 守着;所以「立场只增不改」不靠代码纪律,靠层。

写卡不等于关闭 issue:issue 继续开着当讨论页;后面若另一个立场翻盘,回来改卡,旧内容进卡的历史。反过来,一张直接写的卡后来有人不同意,就开一个 issue 挂到这张卡上当它的讨论页——同样是两个提交:`[issue] raise …`(新 issue,`card` 指向那张卡)+ `[card] link …`(卡的 `issue` 指回来)。

---

## 8. issue 在 Collect 里:一个 layer

issue 是 Collect([collect.md](collect.md))里内置的一个 **layer**:

| | |
|---|---|
| layer 名 | `issue`;分支 `layer/issue`;提交信息以 `[issue]` 开头 |
| 形态 | **`<任意路径>/<名>.issue/`**——一个 issue 一个带后缀的目录,放哪都行;里面 `issue.json` 是本体,可放 `manager.json`;`<名>` 由人起(问题的短标题) |
| schema | `question` / `origin` / `card→card` / `positions[]{claim, origin, arguments[]{stance, evidence, work_id}, spawned_works[]}` / `links[]{type, target→issue}` |
| 行为 | 提问题、加立场、表态、连边、派活、写卡(`decide`)、被开成讨论页(`raise` 带 `card`)——这些是 schema 之上的领域动作,有自己的端点 |
| 层序 | 在 card 之下:issue 是争的过程、只增不改,card 从它派生 |
| 历史 | `git log layer/issue` = 全部辩论序列;`git log -- <路径>.issue/` = 这一个问题的 |

原来的 `manager_work` 字段**退役**,由目录下的 `manager.json` 取代(§3);`GET /api/issues?manager_work=` / `unmanaged=` 改为按 `manager.json` 的继承链解析。issue 的 id 从 `iss_…` 变成**它的路径**(同 card),`iss_…` 前缀退役。

---

## 9. 这篇有意不定的事

- **新 issue 默认谁管**:从 work 标注里冒出的 issue,要不要自动写一个 `manager.json` 指向出处 work(或它的父);还是不写、靠所在文件夹 `manager.json` 的继承。倾向不写——少一个文件,继承链本来就能答;真要专门管再写。
- **论证 work 的结果怎么落成论证**:做完后人来标方向(支持 / 反对 / 中立),还是标注流程自动从它的 round 里提;一个论证 work 能不能同时给多个立场供证据。
- **不是派出去的 work 碰到了这个 issue**:别的 work 在标注时撞上老 issue 并给出证据,走 §2 的挂接路径就够,还是也要记成「事后关联的论证 work」。
- ~~结晶的触发~~:已由 [card.md §2、§4](card.md) 定——写卡 / 改卡是 manager work 里的一个编辑动作,不是阈值触发。
- ~~manager 绑定要不要有历史~~:已定——`manager.json` 在 git 里,`git log` 就是换绑史;前一个 manager 的议事记录当然还算(它在那个 work 的 rounds 里,不会消失)。
