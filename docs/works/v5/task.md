# task —— 为完成一件事而汇集起来的现场(v5 设计)

> **状态:框架稿,未实施。** 本篇只立 task 这一层的大框架:它是什么、跟 shellbase 的 window 是什么关系、里面装什么、session 怎么进来、做完留下什么。字段 / 端点 / 命令等后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 总设计(task / issue / card 三层): [README.md](README.md)
- shellbase window 与块即 URI(task 建在它上面): [shellbase design.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/works/design.md) / [uri.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/works/uri.md)
- v3 explore(先验 / 后验工作区,被 task 并入): [../v3/explore.md](../v3/explore.md)
- v4 逐 round 标注(task → issue 的入口): [../v4/session-annotation.md](../v4/session-annotation.md)

---

## 1. 一句话:task 是「为了做成一件事,把相关的现场都收拢到一起」

一个 task 对应**一件要做成的事**——修一个 bug、调研一个选型、把某个功能做出来。做这件事会用到很多东西:一个跑 Claude Code 的会话、一个跑 Codex 的会话、一个裸终端、几个正在看的网页、一个文件目录。**task 就是把这些现场全部收进同一个容器**,让「这件事」有一个地方待着——从哪开始、中途用了什么、最后怎么样,都在这里。

它是 v5 的**顶层入口**:打开 memory.talk 看到的是 task 列表,而不是 session 列表。session 退到 task 里面,成为 task 的成员。

---

## 2. 跟 shellbase window 的关系:一比一,但重心不同

**每个 shellbase window 就是一个 task。** task 不另起一套运行时——window 有的画布、块、URI、终端 attach、断线重入,task 原样拿来用。打开一个 task,就是打开它那个 window;在 task 里开一个 Codex 会话,就是在 window 里放一个 `codex://` 块。

但两者**重心**不一样:

| | shellbase window | task |
|---|---|---|
| 关心什么 | 屏幕怎么分、每块多大、放在哪 | 有哪些现场、它们是为了什么事汇在一起 |
| 布局 | 是它的核心状态,精确持久化 | **只是一个视图**,可以随时重排、重排不影响 task 本身 |
| 成员身份 | 由 URI 里的 `window` + `block` 位置参数决定 | 由「它属于这个 task」决定,跟摆在画布哪里无关 |
| 生命周期 | 页面开着就在 | 有目标、有开始、有做完 |

所以:**window 是 task 的显示层,task 是 window 的意义层**。window 回答「现在屏幕上有什么」,task 回答「这些东西为什么在一起、事做到哪了」。布局丢了、重排了、换个设备打开分割方式全不一样——task 一点没变,因为 task 记的是**成员和目的**,不是网格坐标。

> 这条决定了一个具体的设计方向:shellbase 里终端身份挂在 `block` 序号上,序号又跟布局绑着;task 里的成员身份要**脱离布局**——一个会话是这个 task 的成员,不因为它被移到别的格子就变成另一个会话。这一点落地时要在 shellbase 的 URI 身份模型上做调整,细节另篇。

---

## 3. task 里装什么:各种「现场」,不只是 agent 会话

task 的成员是**现场**(一个活着的、可以回去看的东西),不限于 code agent:

| 成员类型 | 例子 | 它对 task 的意义 |
|---|---|---|
| **agent 会话** | `claude:///proj`、`codex:///proj` | 干活的主力;它们的 round 是 task 留下的主要痕迹 |
| **终端** | `bash:///proj` | 人自己动手的地方;跑测试、看日志 |
| **浏览器窗口** | `https://…` 的文档、issue 页、dev server 预览 | 为了这件事**看过什么**——也是上下文的一部分 |
| **文件视图** | `file:///proj/src` | 事情落在哪个目录 |

关键是:**它们都是同一件事的一部分**。在 shellbase 里它们是并排的几个块;在 task 里它们是「做这件事时打开过的所有东西」。一个 task 里可以同时跑多个 agent 会话(一个 Claude Code 写代码、一个 Codex 做 review),它们互相看得见对方的工作目录,也共享 task 的目的。

task 本身还有一点自己的东西,不多:**它是什么事**(一句话目标)、**在哪个项目**(工作目录)、**什么时候开的、什么时候算完**。task 不做认知,不打分,不抽卡——那是 issue 和 card 的事。

---

## 4. session 怎么成为 task 的成员:在 task 里打开,就是它的

这是 task 相对 v3 / v4 最实在的一个改变。以前 memory.talk 认 session 归属靠**事后推断**:sync 从平台目录把会话抄进来,再拿 `cwd` 这类物理信号猜它属于哪个 explore。v5 里不用猜——

- **在 task 里开一个 agent 块,这个会话从诞生那一刻就是 task 的成员。** memory.talk 拉起它、看着它跑、记它的 round,归属是原生的。
- 同一个项目目录,可以在不同 task 里各开各的会话,它们互不相干——归属看 task,不看目录。
- 一个会话只属于一个 task。要在别的事里用到它的结论,走 issue / card,不是把会话搬家。
- 从外部平台导入的历史会话(v3 的 sync 路径)继续保留,作为没有 task 归属的会话存在;要不要给它们补一个 task、怎么补,是兼容问题,后面再说。

---

## 5. task 的一生:开工 → 干活 → 做完 → 留下痕迹

粗线条地看,一个 task 就四段:

1. **开工**:说清要做什么事、在哪个项目;memory.talk 拿这句目标去撞 card,把相关的认知先注入进来——这是 recall 在 v5 的落点:**recall 的对象是 task,不再是零散的会话**。
2. **干活**:往 task 里加现场,agent 跑、人看、网页翻。这段时间 task 就是一个 shellbase window,怎么排随便。
3. **做完**:事成了(或者放弃了),task 结束。结束以后成员冻结:会话不再追加 round,现场可以回去看,但不再是干活的地方。
4. **留下痕迹**:task 留下的是它所有成员的记录——agent 会话的 round、看过的网页、动过的目录。这堆痕迹是 **issue 层的原料**:逐 round 标注在这上面做,`#问题` 从这里冒出来。

第 4 段就是 v3 explore 想要的东西,在 task 里天然成立:**一个 task 的会话是它自己提出的问题的先验素材;后面的 task 是这些问题的后验证据**。不用再画一条时间分割线——task 的边界就是那条线。

---

## 6. task 跟 issue / card 怎么接

task 是三层里最「实」的一层,它跟另外两层只有两个接口:

- **往上:task → issue**。task 的痕迹被逐 round 标注,标注里的问题建 / 挂到 issue。一个 issue 记得它是从哪个 task 的哪些 round 冒出来的;一个 task 也能反过来列出「这件事引出了哪些问题、对哪些老问题给了新论证」。
- **往下:card → task**。task 开工时,recall 把命中的 card 注入到 task 里的 agent 会话中。注入的是 card,不是 issue,也不是别的 task 的会话原文。

task 之间**不直接连**。两个 task 有关系,是因为它们碰到了同一个 issue,或者用了同一张 card——关系走认知层,不走任务层。这样 task 可以一直很简单:一个容器、一句目标、一堆现场。

---

## 7. 这篇有意不定的事

- **结束的判定**:人手动点「做完」,还是长时间没动静自动归档,还是两者都有。
- **agent 会话之外的成员留什么痕迹**:浏览器窗口的访问记录、终端里敲过的命令,要留到什么程度才够当 issue 的原料,又不至于把什么都往里塞。
- **一个 window 里能不能有多个 task**:本篇按一比一写。如果实践中「我这个屏幕上同时在做两件事」很常见,再考虑 task 小于 window。
- **task 的层级**:大事拆小事要不要建模成父子 task。本篇不建,先靠 issue 的「细化」边表达事情之间的层级。
- **成员身份脱离布局**怎么落到 shellbase 的 URI 模型上(§2 末),这是唯一需要动 shellbase 的地方,单独一篇。
