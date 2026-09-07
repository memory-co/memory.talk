# collect —— 认知层的容器:层由 schema 定义(v5 设计)

> **状态:框架稿,未实施。** 本篇引入 **Collect** 这个抽象:memory.talk 的认知层不再是「issue 和 card 两套存储」,而是一个 **Collect**——一个 [collectbase](https://github.com/memory-co/collectbase) 仓库;issue 和 card 各是其中的一个 **layer**;layer 由 **schema** 定义,用户写清 schema 就能加自己的 layer。字段 / 命令后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 store(git 存认知层——本篇把「怎么用 git」交给 collectbase): [store.md](store.md)
- v5 issue / card(Collect 里内置的两个 layer): [issue.md](issue.md) / [card.md](card.md)
- collectbase v2 契约(层即分支、路径不相交、`[层名]` 声明、守卫): [DESIGN.md](https://github.com/memory-co/collectbase/blob/main/docs/v2/DESIGN.md) / [branch-topology.md](https://github.com/memory-co/collectbase/blob/main/docs/v2/works/branch-topology.md)

---

## 1. 一句话:Collect 是认知层,layer 由 schema 定义

[store.md](store.md) 定了「card 和 issue 放进一个 git 仓库」。collectbase 正好是「把 git 做成分层记录文件系统」的工具:**每一层一条权威分支、层与层路径不相交、`[层名]` 声明归属、hook 守卫**。v5 不自己再造一套,直接把那个 git 仓库**变成一个 collectbase 仓库**,并给它一个名字:

> **Collect** = memory.talk 的认知层。它是一个 collectbase 仓库;它的每一个 **layer** = 一个名字 + 一段路径 + 一份 **schema**。

于是三层结构里「记事 / 议事」那两层,在存储上统一成一个东西:

```
Collect(一个 collectbase 仓库,~/.memory.talk/memory/)
├── layer/issue ← layer issue:issues/<id>.json schema:question / positions[] / arguments[] / links[] …
├── layer/card ← layer card :cards/**/<slug>.md schema:frontmatter(title / context / links / issue / status)+ 正文
└── layer/<你的> ← 用户自定义的 layer:写清 schema 就行
 stack ← 合并视图:所有 layer 的文件并在一起,日常读写站在这里
```

issue 和 card **只是两个内置的 layer **。它们的对象模型([issue.md](issue.md) / [card.md](card.md))一字不改;改的是它们**住在哪、怎么被管**——从「两个目录」变成「两个 layer」。

---

## 2. 为什么要这一层抽象

三个理由,都是 store.md 想要而裸 git 给不了的:

- **每个 layer 自己一条历史。** `git log layer/card` 只有卡的变化,`git log layer/issue` 只有辩论序列;`git log --first-parent stack` 是全部认知的时间线,每一行自带 `[issue]` / `[card]` 标注。裸 git 里这些要靠路径过滤去拼,而且分支上什么都混在一起。
- **layer 与 layer 之间路径不相交,由 hook 守着。** 一个声明 `[card]` 的提交碰了 `issues/` 下的文件,当场拒绝——包括 `--no-verify`、`reset`、`cherry-pick` 都绕不过。这就是 collectbase 说的「认知卫生」在 memory.talk 里的形态:**不会有一次提交把「争的过程」和「争完的结论」搅在一起**。
- ** layer 是可加的,不用改代码。** collectbase 的 `layers` 文件就是 layer 的清单;加一层 = 加一个名字。memory.talk 在这上面只多要一样东西:**schema**——这个 layer 的文件长什么样。于是「我想记一种新东西」(决策记录、实验日志、人物档案……)变成写一份 schema,而不是往 backend 里加一个包。

一句话:**collectbase 管「层怎么在 git 里成立」,memory.talk 管「每一层里的文件是什么」。**

---

## 3. layer = 名字 + 路径 + schema

一个 layer 要说清三件事:

| 要素 | 是什么 | issue | card |
|---|---|---|---|
| **名字** | = layer 名 = 提交信息里的 `[层名]` = 分支 `layer/<名字>` | `issue` | `card` |
| **路径** | 这个 layer 的文件住在哪(collectbase 不强制每层一个目录,但 memory.talk 的内置 layer 各占一个) | `issues/<id>.json` | `cards/**/<slug>.md` |
| **schema** | 文件长什么样:格式 + 字段 + 哪些字段是引用(指向别的 layer 的对象) | JSON;`question` `origin` `manager_task` `card→card` `positions[]` … | markdown + frontmatter;`title` `context` `links[]→card` `issue→issue` `status` |

schema 决定的事:

- **读**:通用的读 / 列 / 历史 / 检索,按 schema 解析文件就能做,不需要为每个 layer 写代码。
- **写**:通用的建 / 改 / 废弃,按 schema 校验后落盘 + `[layer 名]` 提交。
- **引用**:schema 里标出「这个字段指向哪个 layer 的对象」,于是 card.issue、issue.card、card.links 这些跨 layer 的边有了统一的表达;顺链接走(store.md §5 的检索方式)靠它。
- **目录**:哪个字段是标题、按什么分目录——召回时给 agent 的那份目录由此生成。

内置 layer 除了 schema 还带**行为**:issue 的「加立场 / 表态 / 绑 manager / 派活」、card 的「从 issue 写卡 / 对卡开讨论页」,这些是 schema 之上的领域动作,有自己的端点。**用户自定义的 layer 只有 schema,没有行为**——通用 CRUD 就是它的全部;真需要行为,那就是一个新的内置 layer。

---

## 4. 层序:谁在下,谁在上

collectbase 的层是有序的:**事实在最下,推论在上;上层改不动下层**。memory.talk 的两个内置 layer 怎么排,按「谁更接近记录、谁更接近结论」:

```
上 card ← 争完的结论;可改、可废弃(维基式);从 issue 派生
下 issue ← 争的过程;立场 / 论证只增不改;更接近证据
```

issue 在下、card 在上:card 是从 issue 里争出来的,改 card 不能顺手改 issue 的记录——这正是 issue.md 说的「立场只增不改」在存储层的保证。但注意两点:

- **这不是 collectbase 意义上的「事实层」。** collectbase 的最底层是「智能体够不着」的观测(会话记录、命令输出);memory.talk 里那一层现在**不在 git 里**——task 的痕迹是裸文件([store.md §4](store.md))。将来若把 rounds 也纳入 Collect 当事实层,它会排在 issue 之下;本篇不做,列在 §7。
- **用户自定义的 layer 排在哪**,由用户在 `layers` 里声明顺序时决定。默认建议放在最上(它们多半是更高层的推论)。

---

## 5. 「一个决定一个 commit」怎么变

store.md 说:争出结果写卡,issue 记结论 + card 建正文,**同一个 commit**。collectbase 说:**一个提交只能属于一层**——跨层的提交恰好就是把过程和结论搅在一起的那个动作,必须拆。

两条都对,取 collectbase 的:**一个决定 = 两个相邻的提交,各在自己的层**。

```
git log --first-parent stack
 a1b2c3d [card] write memory.talk/配置只来自环境变量 Decision: dec_…
 9f8e7d6 [issue] decide iss_…#p2 -> card memory.talk/配置只来自环境变量 Decision: dec_…
```

因果不丢:两个提交带同一个 `Decision:` trailer,`--first-parent stack` 上它们相邻;而且**层的边界让它们比原来更清楚**——哪一半是「记录了一个结论」、哪一半是「写了一个结论」,一眼可分。`discuss:`(对卡开讨论页)同理拆成 `[issue]` + `[card]`。

服务层保证两个提交要么都成、要么都不成(第二个失败就 reset 第一个——collectbase 允许在权威分支上 FF,回退是我们自己的事务逻辑)。

---

## 6. 跟现有设计的关系

| | 之前 | 引入 Collect 之后 |
|---|---|---|
| memory/ 仓库 | 裸 git,一条 main | collectbase 仓库:`layer/issue`、`layer/card`、`stack`,`cb init --layers issue,card` |
| issue / card 的对象模型 | issue.md / card.md | **不变** |
| 文件形态与路径 | `issues/<id>.json`、`cards/**/<slug>.md` | **不变**,成为各层的路径 |
| 提交信息 | `card: write …` / `issue: argue …` | `[card] write …` / `[issue] argue …`(动词不变,层名前置) |
| 跨对象的决定 | 一个 commit | 两个相邻提交 + 同一个 `Decision:` trailer(§5) |
| 历史 | `git log -- <path>` | 同,外加 `git log layer/<名>` 看整层 |
| 加一种新对象 | 改 backend | 写一份 schema + `layers` 里加一行 |
| 谁改不动谁 | 靠代码纪律 | hook 守着:上层改不动下层,跨层提交被拒 |

store.md 的两条原则不变:**认知层进 git,现场层用裸文件**。Collect 只是把「进 git」这一半做成了有层语义的。

---

## 7. 这篇有意不定的事

- **schema 用什么写**:JSON Schema、一份 YAML 字段表、还是直接一个 pydantic 类文件。内置 layer 现在就是 pydantic 类;用户的 layer 要能不写 Python——倾向 YAML 字段表 + 少量约定(哪个字段是标题、哪个是引用)。
- **通用 API 的形状**:`/api/collect/<class>/...` 一套 CRUD + 历史 + 检索,内置 layer 的专用端点(`/api/issues/...` `/api/cards/...`)是不是它上面的别名。
- **要不要把 rounds 纳入 Collect 当事实层**:那会让 task 的痕迹进 git、成为 issue 之下真正的「地板」,collectbase 的分层语义才完整;代价是 store.md §4 的「过程不进 git」被推翻。先不做。
- **跨 layer 引用要不要校验**:card.issue 指向的 issue 必须存在吗;删 / 废弃时要不要检查反向引用。collectbase 明确「不管文件之间的关系」,这是 memory.talk 自己的事;倾向只在写时校验存在、不做级联。
- **两个提交的事务**(§5):第一个成、第二个败时的回退,是 `reset` 权威分支(需要绕过「只进不退」)还是补一个反向提交。倾向后者,历史更诚实。
- **`stack` 之外要不要给每个 layer 一条工作分支**:collectbase 说站在 `stack` 上声明哪层都行;memory.talk 的服务进程是唯一写者,站 `stack` 就够。
