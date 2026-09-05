# store —— git 存认知,裸文件存现场,没有数据库(v5 设计)

> **状态:框架稿,未实施。** 本篇只立 v5 存储的大框架:card 和 issue 放进一个 git 仓库,task 用裸文件,SQLite 整个去掉,搜索索引降为可重建的派生物。目录布局、文件格式、commit 规范后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 三层(存的就是这三样): [task.md](task.md) / [issue.md](issue.md) / [card.md](card.md)
- v3 file-canonical 模式(文件是 canonical、SQLite 和向量库是派生——本篇是它的延伸和简化): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)
- v3 searchbase(向量 + FTS 索引底座,继续用,只是不再有 SQLite 陪着): [../v3/searchbase-extraction.md](../v3/searchbase-extraction.md)
- v4 存储(file 罐 + SQLite 瘦索引 + 运行态计数——v5 不再需要运行态): [../v4/card.md §8](../v4/card.md)

---

## 1. 一句话:认知层进 git,现场层用裸文件,中间没有数据库

```
~/.memory.talk/
├── memory/          ← 一个 git 仓库:cards/ + issues/。认知的 canonical,连同它的全部历史
├── tasks/           ← 裸文件:task 树、画布、会话 round。现场的 canonical,原子写,不进 git
└── index/           ← 派生:向量 + FTS 索引,随时可从上面两处重建,丢了不心疼
```

三条原则:

- **card 和 issue 在 git 里**。它们是「认知」——会被改、会被争、要问「为什么变成这样」;git 天生就是回答这个问题的工具。
- **task 是裸文件**。它是「现场」——画布状态、终端登记、会话 round;变化频繁、体量大、要的是原子写和唯一权威,不是历史叙事。这正是 shellbase 的状态模型([task.md §3](task.md)),原样继承。
- **没有 SQLite**。v3 / v4 的 SQLite 干两件事:派生索引、可变运行态(顶踩计数、read / recall 计数)。v5 的 card 没有计数([card.md](card.md)),issue 的论证是 append-only 的文件,task 是裸文件——**可变运行态消失了**;剩下的派生索引由 searchbase 承担。SQLite 没剩下什么非它不可的事。

---

## 2. 为什么是 git:因为它是一条时间线,时间线里有因果

memory.talk 从 v3 起就坚持「文件是 canonical」。但文件只有**现在**,没有**过去**——v3 / v4 为了留过去,自己造了 events.jsonl、append-only 的 rounds、Position 的分叉血缘、review 日志。这些都是在手工重建一条时间线。

git 就是那条时间线,而且是带**因果**的:

- **每个 commit 是一个时刻**,有时间、有作者、有理由(message)。一张卡为什么长这样,`git log` 这张卡就是它的完整故事;一个 issue 是怎么争起来的,它的 commit 序列就是辩论记录。
- **parent 链就是因果链**。一次改卡,是因为某个 issue 议出了结果——那次 commit 同时动了 issue(记下结论)和 card(改正文),**因果在同一个 commit 里**,不用另外建一张「谁导致谁」的表。「一个决定」在存储上就是一个 commit。
- **card 要的「可编辑 + 有历史」是 git 的原生能力**:维基的编辑历史 = `git log -p`,回滚 = `git revert`,谁改的 = author,为什么改 = message。不需要再设计一套版本模型。
- **issue 要的「立场和论证只增不改」也是 git 的原生能力**:append 一条论证 = 一个 commit;想改历史必须显式 rewrite,而这正是我们不允许的。不变性由工具兜底,不靠代码纪律。
- **explore 的先验 / 后验在 git 里是免费的**:一个 task 开工那一刻对应仓库的一个 commit,线之前的认知是它的先验,线之后的 commit 是后验。不用再画分割线。

反过来说,如果不用 git,v5 就得自己实现:版本历史、原子的跨对象变更、作者和理由的记录、不可篡改的追加日志——每一样 git 都已经做得比我们好。

> **git 在这里是存储引擎,不是协作工具。** 不假设用户会 `git log` 去看(虽然可以);memory.talk 自己的 read / search / recall 从工作树和历史里读。分支、远端、合并这些能力先不依赖——它们是**将来可能的好处**(§6),不是现在的设计前提。

---

## 3. 什么算一个 commit:一个有意义的动作

commit 的粒度是**一个认知层的动作**,不是一次文件保存:

| 动作 | 动了什么 | 谁提交 |
|---|---|---|
| 标注里冒出新问题 | 新建一个 issue | 标注流程(以 task + round 为出处) |
| 加立场 / 加论证 / 换 manager / 派出论证 task | 那个 issue 追加一条 | manager task 里的人或 agent |
| 争出结果,写卡或改卡 | issue 记结论 + card 改正文,**同一个 commit** | manager task 里的人或 agent |
| 直接写一张没什么可争的卡 | 新建一个 card | 人或 agent |
| 废弃一张卡 | card 标废弃(文件留着) | 人或 agent |

message 里带**理由**和**出处**(哪个 task、哪些 round),author 区分人和 agent(agent 带上它所在的 task)。这些不是装饰——它们就是「时间线里的因果」本身;没有理由和出处的 commit,时间线退化成流水账。

task 那边的动作(开工、拆子 task、状态变化、做完)**不进 git**,但 task 会被 commit 引用(出处、manager、派出),引用跨过 git 边界没问题——task id 是稳定的,round 是 append-only 的。

---

## 4. 裸文件那半:task 沿用 shellbase 的状态模型

task 的存储就是 shellbase 的 state 目录,原生实现、逻辑一致([task.md §3](task.md)):

- **每个 task 一个目录**,树用目录嵌套或父指针表达(布局细节后议);里面是 task 自己的元信息(目标、状态、父子)、画布(布局 + 每块的 URI)、终端登记、以及每个会话的 `rounds.jsonl`。
- **原子写、单写者、无缓存直读**——shellbase 的三条读写纪律原样继承。
- **会话 round 是 append-only 的裸文件**,跟 v3 一样;它体量大、增长快、不需要「为什么」,所以不进 git。task 自己的时间线(什么时候开的、什么时候变状态、什么时候完)由 task 目录下一个小的 append-only 事件文件记着——这是 v3 events.jsonl 在 v5 唯一保留的地方。

为什么 task 不进 git,再说一遍:git 记的是**决定**,task 记的是**过程**。把画布每次重排、终端每次 attach、agent 每一轮输出都提交进 git,时间线会被淹没,真正的因果反而找不到。

---

## 5. 索引:派生、可重建、不是 canonical

searchbase(向量 + FTS,LanceDB)继续用,角色比 v3 更纯:**只是 card / issue / session 的检索索引**,从 git 工作树和 task 目录建出来,`rebuild` 随时从头重建。它不存任何别处没有的东西——v3 里 SQLite 兼任的「派生索引」这一半也归它;「运行态」那一半 v5 根本没有。

索引读 git 的**工作树(HEAD)**,不读历史——召回查的是「现在的事实」。要历史的时候(某张卡的故事、某个 issue 的辩论序列)直接读 git,不经索引。

---

## 6. 这条路顺带带来的东西(不作为设计前提)

- **可移植**:整个认知层就是一个 git 仓库,`clone` 即迁移,换机器、换后端都不丢历史。
- **可审计**:`git log` 就是审计日志;任何一条认知都能回答「谁、什么时候、为什么」。
- **可分享 / 可同步**:一个 git 仓库天然可以有远端。多台机器的 memory.talk 同步认知、团队共享一份认知层,都是 push / pull 的事——**但这是将来的可能性**,v5 先按单机单仓设计,不为多端引入任何分支或合并逻辑。
- **可回滚**:agent 改坏了一张卡,`revert` 那个 commit 就行,不需要为卡单独设计撤销。

---

## 7. 这篇有意不定的事

- **单仓还是分仓**:card 和 issue 在一个仓库里(跨对象的因果能落在同一个 commit,本篇倾向这个)还是各一个仓库。
- **并发写**:一台机器上多个 task 的 agent 同时往认知层提交——串行锁(简单,本篇倾向)还是每个 task 一个分支再合并(复杂,但更 git)。
- **commit 粒度的边界**:标注流程一轮冒出十个问题,是十个 commit 还是一个;一次「争出结果」改了三张卡,是一个还是三个。倾向「一个决定一个 commit」,但决定的边界要定。
- **task 目录要不要也用 git 管极少数的东西**:比如 task 的目标和状态变化。本篇按「不进」写,靠事件文件留时间线;若实践中发现 task 层也需要因果,再议。
- **v3 数据怎么进来**:insight 投影成 card / issue 是一批初始 commit;旧的 SQLite 计数(review / read / recall)不迁——v5 没有它们的位置。
- **searchbase 还需不需要 FTS 之外的结构化查询**(比如「这个 task 管的所有 issue」):从 git 工作树扫、还是索引里多存几列。倾向前者,量级不大。
