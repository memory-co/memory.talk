# collections —— 认知层的容器:层是一个 check(v5 设计)

> **状态:框架稿,未实施。** 本篇引入 **Collections** 这个抽象:memory.talk 的认知层不再是「issue 和 card 两套存储」,而是一个 **Collections**——一个 [collectbase](https://github.com/memory-co/collectbase) 仓库;issue 和 card 各是其中的一个 **layer**;layer 由 **schema** 定义,用户写清 schema 就能加自己的 layer。字段 / 命令后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 store(git 存认知层——本篇把「怎么用 git」交给 collectbase): [collections-store.md](collections-store.md)
- v5 issue / card(Collections 里内置的两个 layer): [issue.md](issue.md) / [card.md](card.md)
- v5 collections layer(用户怎么设计一个自己的层): [collections-layer.md](collections-layer.md)
- v5 origin(最底层:外部来的、未消化的原文;上层改不动): [origin.md](origin.md)
- collectbase v2 契约(层即分支、路径不相交、`[层名]` 声明、守卫): [DESIGN.md](https://github.com/memory-co/collectbase/blob/main/docs/v2/DESIGN.md) / [branch-topology.md](https://github.com/memory-co/collectbase/blob/main/docs/v2/works/branch-topology.md)

---

## 0. 名字:为什么叫 collections

这一层最初叫 Collect(动词,「收拢」),2026-09-10 改名 **collections**。理由和 [work.md §0](work.md) 一样,名字要和别的层对齐:

- **名词,不是动词。** works、sessions、users、layers 都是名词;认知层的容器也该是一个名词——它是「收拢起来的那些东西」,不是「收拢」这个动作。
- **有复数形态。** 它装的是很多份材料、很多个问题、很多张卡,而且还能分出很多个 layer;复数说的就是这个。磁盘上、API 上也一律用复数:`~/.memory.talk/collections/`、`/api/collections/`,和 `works/`、`/api/works/` 一个样。
- **和 collectbase 分开。** collectbase 是被参考的那个工具(v5 不依赖它,自己实现了同样语义的分层 git);collections 是 memory.talk 自己的对象。两个词长得像,但一个是别人的项目名,一个是我们的层名。

代码里对应的改名:`services/collections/`、`/api/collections/`、`CollectionsService`。

---

## 1. 一句话:collections 是认知层,layer 是一个 check

[collections-store.md](collections-store.md) 定了「card 和 issue 放进一个 git 仓库」。collectbase 正好是「把 git 做成分层记录文件系统」的工具:**每一层一条权威分支、层与层路径不相交、`[层名]` 声明归属、hook 守卫**。v5 不自己再造一套,直接把那个 git 仓库**变成一个 collectbase 仓库**,并给它一个名字:

> **Collections** = memory.talk 的认知层。它是一个 collectbase 仓库;它的每一个 **layer** = 一个名字 + 一段路径 + 一个 **check**(这次提交过不过)。

于是三层结构里「记事 / 议事」那两层,在存储上统一成一个东西:

```
Collections(一个 collectbase 仓库,~/.memory.talk/memory/)
├── layer/origin   ← origin:任何**不带层后缀**的文件或目录          schema 极薄:原文 + 可选 meta;最底层,只读
├── layer/issue    ← issue :任何 `<名>.issue/` 目录(里面 readme.md + meta.yaml + positions/*.md)  标题 = 目录名;每个立场一个文件;meta.yaml 放边和 manager 的排序
├── layer/card     ← card  :任何 `<名>.card/` 目录(里面 readme.md + meta.yaml)  标题 = 目录名;meta.yaml 放 context / links / issue
└── layer/<你的>   ← 用户自定义的 layer:`<名>.<层>/`,~/.memory.talk/layers/<名>.py 里一个 Layer 子类就行
    stack          ← 合并视图:所有 layer 的文件并在一起,日常读写站在这里
```

**层不占目录,对象带后缀。** 没有 `issues/`、`cards/` 这种按层分的顶层目录——一个对象是哪一层,看它目录名的后缀(`.issue/`、`.card/`);没有后缀的一切都是 origin。于是目录树可以按**主题**组织,同一个文件夹里原文、讨论页、词条并排:

```
memory.talk/
├── manager.json                              ← 这一片归谁管(任何层的变动都打过去)
├── 配置/
│   ├── 旧的 settings 方案.md                  ← origin:一份原文
│   ├── 该走文件还是环境变量.issue/            ← issue:围绕它的讨论
│   │   ├── readme.md
│   │   ├── meta.yaml
│   │   ├── positions/p1.md
│   │   └── manager.json
│   └── 配置只来自环境变量.card/               ← card:争完的结论
│       ├── readme.md
│       └── meta.yaml
└── design/
    └── v5-总设计.pdf → blob/…                ← origin:二进制外置
```

这就是「在文件系统里做融合」:分层是 git 分支上的事(每层自己的历史、路径不相交、hook 守卫),**布局是人的事**——collectbase 本来就说「布局完全自由,上层文件可以放在下层文件旁边」,memory.talk 只多加一条:用后缀标身份。

issue 和 card **只是两个内置的 layer**。它们的对象模型([issue.md](issue.md) / [card.md](card.md))一字不改;改的是它们**住在哪、怎么被管**——从「两个目录」变成「两个 layer」。

---

## 2. 为什么要这一层抽象

三个理由,都是 collections-store.md 想要而裸 git 给不了的:

- **每个 layer 自己一条历史。** `git log layer/card` 只有卡的变化,`git log layer/issue` 只有辩论序列;`git log --first-parent stack` 是全部认知的时间线,每一行自带 `[issue]` / `[card]` 标注。裸 git 里这些要靠路径过滤去拼,而且分支上什么都混在一起。
- **layer 与 layer 之间路径不相交,由 hook 守着。** 一个声明 `[card]` 的提交碰了某个 `.issue/` 目录里的文件,当场拒绝——包括 `--no-verify`、`reset`、`cherry-pick` 都绕不过。这就是 collectbase 说的「认知卫生」在 memory.talk 里的形态:**不会有一次提交把「争的过程」和「争完的结论」搅在一起**。
- **layer 是可加的,不改包里的代码。** collectbase 用根上的 `layers` 文件当锚定;memory.talk 对应的是根上的 **`collections.json`**——整个 collections 的配置 + `layers[]` 清单(最底在前,只有名字和 `builtin`);用户层是 `~/.memory.talk/layers/<名>.py` 里一个 `Layer` 子类,启动时载入并登记进去。加层就是加一项、开一条从始祖出发的分支;`git log collections.json` 是层的变化史。

一句话:**collectbase 管「层怎么在 git 里成立」,memory.talk 管「每一层里的文件是什么」。**

---

## 3. layer = 名字 + 路径 + check

一个 layer 要说清三件事:

| 要素 | 是什么 | issue | card |
|---|---|---|---|
| **名字** | = layer 名 = 提交信息里的 `[层名]` = 分支 `layer/<名字>` | `issue` | `card` |
| **路径** | 对象怎么认:**目录名后缀 `.<层>/`**,放在树的任何位置;没有后缀的就是 origin | `<任意路径>/<名>.issue/`(readme.md + meta.yaml + positions/*.md) | `<任意路径>/<名>.card/`(readme.md + meta.yaml) |
| **协议** | 一份 YAML:目录里允许哪些路径、每个文件的 formatter(字段 / 枚举 / 引用 / 正文)、哪些必需、哪些只能追加;后端用它校验,前端用它画表单([collections-layer.md](collections-layer.md)) | `readme.md`(markdown)+ `meta.yaml`(`links[]` `positions[]` `summary`)+ `positions/*.md`(markdown);别的文件拒绝 | `card.md`(markdown + frontmatter;`title` `context` `links[]→card` `issue→issue`) |

schema 决定的事:

- **读**:通用的读 / 列 / 历史 / 检索,按 schema 解析文件就能做,不需要为每个 layer 写代码。
- **写**:通用的建 / 改 / 删,按 schema 校验后落盘 + `[layer 名]` 提交。删也是提交——文件没了,历史在。
- **引用**:schema 里标出「这个字段指向哪个 layer 的对象」,于是 card.issue、issue.card、card.links 这些跨 layer 的边有了统一的表达;顺链接走(collections-store.md §5 的检索方式)靠它。
- **目录**:哪个字段是标题、按什么分目录——召回时给 agent 的那份目录由此生成。

层**没有行为**,内置的也没有:做任何事都是往目录里提交文件,层的 check 决定过不过。issue 的「加立场 / 加论证 / 排序」、card 的「从 issue 写出来 / 开讨论页」都是几次普通提交(见 [issue.md §3](issue.md))。

---

## 4. 层序:谁在下,谁在上

collectbase 的层是有序的:**事实在最下,推论在上;上层改不动下层**。memory.talk 的三个内置 layer 怎么排,按「谁更接近记录、谁更接近结论」:

```
上   card    ← 争完的结论;可改、可删(维基式,git 记历史);从 issue 派生
     issue   ← 争的过程;立场 / 论证只增不改;从 origin 消化而来
下   origin  ← 事实:外部来的、原样的、未消化的材料;上层改不动。见 [origin.md](origin.md)
```

origin 在最底、issue 在中、card 在上:issue 从 origin 消化出来,card 从 issue 争出来;改 card 不能顺手改 issue 的记录,改 issue 不能碰 origin 的原文。origin 就是 collectbase 意义上的**事实层**——「智能体够不着的地板」。两点说明:

- **work 的痕迹(rounds)仍不在 Collections 里**——它是本实例自己的过程,裸文件([collections-store.md §4](collections-store.md));值得长期当证据的那几轮,摘录一份进 origin([origin.md §6](origin.md))。
- **用户自定义的 layer 排在哪**,按 [collections-layer.md §2](collections-layer.md):引用谁就排在谁上面;所有层都引用 origin,所以都在它之上。

---

## 5. 谁做的:commit 的 author 就是 user

collections 的每个动作是一个 commit,做它的人(请求头 `X-Memory-Talk-User`)就是 commit 的 **author**——立场谁提的、论证谁给的、卡谁改的,全在 `git log` / `git blame` 里,对象里不另存 user 字段。agent 做的提交挂在驱动它的 user 名下,body 的 `Work:` 记它在哪个 work 里做的。没带身份的提交 author 退回服务配置的默认名。详见 [user.md §5](user.md)。

---

## 6. 「一个决定一个 commit」怎么变

collections-store.md 说:争出结果写卡,issue 记结论 + card 建正文,**同一个 commit**。collectbase 说:**一个提交只能属于一层**——跨层的提交恰好就是把过程和结论搅在一起的那个动作,必须拆。

两条都对,取 collectbase 的:**一个决定 = 两个相邻的提交,各在自己的层**。

```
git log --first-parent stack
 a1b2c3d [card] write memory.talk/配置只来自环境变量 Decision: dec_…
 9f8e7d6 [issue] decide iss_…#p2 -> card memory.talk/配置只来自环境变量 Decision: dec_…
```

因果不丢:两个提交带同一个 `Decision:` trailer,`--first-parent stack` 上它们相邻;而且**层的边界让它们比原来更清楚**——哪一半是「记录了一个结论」、哪一半是「写了一个结论」,一眼可分。`discuss:`(对卡开讨论页)同理拆成 `[issue]` + `[card]`。

服务层保证两个提交要么都成、要么都不成(第二个失败就 reset 第一个——collectbase 允许在权威分支上 FF,回退是我们自己的事务逻辑)。

---

## 7. 跟现有设计的关系

| | 之前 | 引入 Collections 之后 |
|---|---|---|
| memory/ 仓库 | 裸 git,一条 main | collectbase 仓库:`layer/origin`、`layer/issue`、`layer/card`、`stack`,`cb init --layers origin,issue,card` |
| issue / card 的对象模型 | issue.md / card.md | **不变** |
| 文件形态与路径 | `issues/<id>.json`、`cards/**/<slug>.md`(按层分目录) | **对象变目录、带后缀、放哪都行**:`<名>.issue/`(readme.md + meta.yaml + positions/)、`<名>.card/`(readme.md + meta.yaml);不再有按层分的顶层目录 |
| 提交信息 | `card: write …` / `issue: argue …` | `[card] write …` / `[issue] argue …`(动词不变,层名前置) |
| 跨对象的决定 | 一个 commit | 两个相邻提交 + 同一个 `Decision:` trailer(§6) |
| 历史 | `git log -- <path>` | 同,外加 `git log layer/<名>` 看整层 |
| 加一种新对象 | 改代码 | `~/.memory.talk/layers/` 放一个 `.py`(一个 `Layer` 子类),重启 |
| 谁改不动谁 | 靠代码纪律 | hook 守着:上层改不动下层,跨层提交被拒 |

collections-store.md 的两条原则不变:**认知层进 git,现场层用裸文件**。Collections 只是把「进 git」这一半做成了有层语义的。

---

## 8. 这篇有意不定的事

- ~~schema 用什么写~~:已定——不用 schema,用户层就是一个 `Layer` 子类的 `.py`,和内置层一样写 `check`([collections-layer.md](collections-layer.md))。
- **通用 API 的形状**:`/api/collections/<class>/...` 一套 CRUD + 历史 + 检索,内置 layer 的专用端点(`/api/issues/...` `/api/cards/...`)是不是它上面的别名。
- ~~要不要把 rounds 纳入 Collections 当事实层~~:已定——地板是 [origin](origin.md)(外部材料),rounds 整体仍不进 git;要留的几轮摘录进 origin。
- **跨 layer 引用要不要校验**:card.issue 指向的 issue 必须存在吗;删时要不要检查反向引用。collectbase 明确「不管文件之间的关系」,这是 memory.talk 自己的事;倾向只在写时校验存在、不做级联。
- **两个提交的事务**(§6):第一个成、第二个败时的回退,是 `reset` 权威分支(需要绕过「只进不退」)还是补一个反向提交。倾向后者,历史更诚实。
- **`stack` 之外要不要给每个 layer 一条工作分支**:collectbase 说站在 `stack` 上声明哪层都行;memory.talk 的服务进程是唯一写者,站 `stack` 就够。
