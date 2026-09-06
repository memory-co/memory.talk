# member —— task 里的一个现场(v5 设计)

> **状态:框架稿,已有最简实现。** 本篇只立 member 这一层的大框架:它是什么、为什么要从「画布上的块」里独立出来、跟 panel / server / session 三个邻居怎么分工、一生几步、留下什么。字段见 [`../../structure/v5/task.md`](../../structure/v5/task.md#member),端点见 [`../../api/v5/tasks.md`](../../api/v5/tasks.md)。

相关:
- v5 task 树(member 住在 task 里): [task.md](task.md)
- v5 protocol server(member 是 server 建出来的): [protocol-server.md](protocol-server.md)
- v5 issue(issue 的出处和证据指向 member 留下的 round): [issue.md](issue.md)
- shellbase 的会话身份(`window` + `block` 位置参数——本篇有意偏离它的那一点): [uri.md §4](https://github.com/memory-co/shellbase/blob/main/docs/v1/works/uri.md)

---

## 1. 一句话:member 是「task 的一个成员」,一个活着的现场

task 是为了做成一件事把现场收拢到一起的容器([task.md §1](task.md));**member 就是收进去的每一个现场**:一个跑着 Codex 的会话、一个裸终端、一个正在看的网页。它有三样东西:

- **身份**:一个稳定的 id,`<task_id>-m<n>`,在 task 里顺序编号。
- **它是什么**:一个 URI(`codex:///proj`)+ 建它的 server(`codex`)+ 解析出的工作目录。
- **它活没活着**:现场在不在(tmux 会话还在不在)——这不存,每次问 server。

member **不是**布局里的一个格子,也**不是**会话记录本身;那两个是它的邻居(§3)。

---

## 2. 为什么要有它:身份必须脱离布局

shellbase 里没有 member 这个概念。块的身份写在 URI 的 `window` + `block` 两个位置参数里:同一个 `codex:///proj` 在 `main` 窗口的第 1 格和第 2 格是两个现场,换个格子就换了身份。这在「画布就是全部」的 shellbase 里是对的——块在哪,它就是谁。

v5 的 task 不是画布,画布只是它的视图([task.md §3](task.md)):**布局可以随时重排,重排不改变 task**。这就要求现场的身份**不能挂在格子上**——否则把 Codex 那块从左边拖到右边,后端就认为你关了一个会话又开了一个新的,round 断成两截,issue 指回来的出处也断了。

所以 v5 把「现场的身份」从块里抽出来,单独立一个对象:**member**。它是 v5 原生实现时**唯一有意偏离 shellbase** 的地方([protocol-server.md §2](protocol-server.md)):

| | shellbase 的块 | v5 的 member |
|---|---|---|
| 身份在哪 | URI 里的 `?window=…&block=…` | 自己的 id,`<task_id>-m<n>` |
| 换个格子 | 换了身份(新现场) | 还是它(布局是视图) |
| 关掉页面 | 现场还在(tmux),下次按同一 URI 重入 | 同,按 member id 重入 |
| 谁记着它 | 布局文件里的 panel 记录 | task 的 `members.json`(唯一权威) |

---

## 3. 三个邻居:panel、server、session

member 夹在三个概念中间,分工要清楚:

```
panel(画布上的格子) ──装着──▶ member(现场的身份) ──由谁建──▶ server(codex / bash / http / default)
                                      │
                                      └──留下──▶ rounds.jsonl(会话痕迹,issue 的原料)
```

- **panel 是视图,member 是实体**。panel 记 `{id, uri, member, x, y, w, h}`,其中 `member` 指向一个成员;panel 可以删、可以重排、可以整张画布清空重画,member 不动。反过来,member 也不要求有 panel——一个成员可以暂时没被摆在画布上(比如画布重画时),它还活着。
- **server 建它,task 记它**。server 只回答「这个 id 的现场活没活着、怎么看、怎么驱动」,**不记 task**;member 属于哪个 task、什么时候开的、最近什么时候重入,全在 task 目录的 `members.json`。server 重启后,task 层拿登记去 server 那里把现场一个个取回来([protocol-server.md §4](protocol-server.md))。
- **member 不是 session,session 是它留下的痕迹**。v3 的 session 是「事后导入的对话记录」;v5 里 agent 类 member 跑着的时候,它的 round 从平台记录文件里流出来,追加进 `sessions/<member_id>/rounds.jsonl`。member 是活的现场,rounds 是它的痕迹;member 销毁了,痕迹留着。

一句话:**panel 是怎么摆,member 是它是谁,server 是怎么建,rounds 是它留下了什么。**

---

## 4. 一生四步:attach → reattach → detach / freeze

1. **attach**(在 task 里打开一个块)。task 层先登记一条成员、分配 id;拿协议去 server 那里寻址;server 用这个 id 幂等地建现场——终端类就是起一个 **tmux 会话,会话名 = member id**;交回窗(嵌进画布)和把手(留给 task 层观测)。建现场失败,登记回滚,不留半个成员。
2. **reattach**(重入)。换设备、刷新页面、服务重启之后,拿 member id 再 open 一次:现场还在就直接取回,不在就按原 URI 重建。**同一个 id 永远是同一个现场**——这是 tmux `new -A` 的语义,也是 `*muxd` 规范的 M4。
3. **detach**(关闭即回收)。销毁现场 + 删登记。跟 shellbase 一样,关块不是从画布上摘掉,是真的 kill。
4. **freeze**(task 结束)。task 做完或放弃,所有成员的现场销毁、**登记留着**:成员不再活着、不能再 attach,但还能回去看它的 rounds。这是「结束以后成员冻结,现场可以回去看但不再是干活的地方」([task.md §6](task.md))在 member 上的落法。

detach 和 freeze 的差别:detach 是「这个现场我不要了」,登记一起删;freeze 是「这件事做完了」,登记作为痕迹的索引留下。

---

## 5. 一个 member 只属于一个 task,一个确定的节点

- **在 task 里打开的,就是它的**。归属是原生的、在创建那一刻定下的,不靠 cwd 事后推断(v3 explore 的做法)。同一个项目目录可以在不同 task 里各开各的成员,互不相干。
- **一个成员只属于一个 task,而且是树上一个确定的节点**,不属于「整棵树」。父 task 看不到子 task 的成员——它看到的是子 task 的状态。
- **不搬家**。要在别的事里用它的结论,走 issue / card,不把成员挪到另一个 task 下。member id 里带着 task id,搬家在身份上就说不通。

---

## 6. member 留下什么:rounds,以及 issue 指回来的路

agent 类 member(claude / codex / kimi)的把手多一项 `rounds`:按 cwd + 成员创建时间在平台的记录目录里定位那份会话记录,把新 round 追加进 `rounds.jsonl`,按平台自己的消息 id 去重。这是 member 对认知层唯一的贡献,也是最重要的:

- **issue 的出处和论证的证据都指向这里**:`origin = {task_id, rounds: […]}`,rounds 是 `rounds.jsonl` 里的下标。逐 round 标注、`#问题` 建 issue,全在这份文件上做。
- **只追加**。round 是过程,不是决定;不进 git,也从不改既有行。
- **bash / http 类 member 没有 rounds**。裸终端的痕迹只有一块屏幕(`capture`),网页什么都不留——它们对 task 的意义是「做这件事时打开过什么」,记在登记里就够了。要不要给终端留命令历史、给网页留访问记录,是 [task.md §8](task.md) 留的那条待定。

---

## 7. 这篇有意不定的事

- **member 能不能换 URI**:shellbase 的做法是「改 URI = 销毁重建」。v5 倾向同样——member 的 URI 是它身份的一部分,要换就 detach 再 attach 一个新的;但「同一个 agent 会话换个工作目录」这种需求真出现了再议。
- **一个 member 能不能被多个 panel 装**:同一个 tmux 会话在画布上开两个格子镜像,shellbase 靠完整 URI 显式做到。v5 的 panel 记 `member`,技术上允许两个 panel 指同一个成员;要不要允许,看协作(多人看同一个 agent)是不是真需求。
- **freeze 之后能不能「解冻」**:task 从 done 改回 doing,成员要不要跟着能重新 attach。倾向能——登记还在,reattach 会按原 URI 重建;但 agent 的会话记录已经是新的一份,round 会接着追加还是另起,要定。
- **rounds 的同步时机**:现在是读的时候顺手同步(pull)。要不要在 member 活着的时候后台盯着记录文件(watch),让标注流程能实时看到新 round——这跟「逐 round 标注是在 task 进行中做还是做完再做」绑在一起。
- **非 tmux 的现场怎么算活着**:http 类 member 永远 `alive`,因为没有进程。换成 webmuxd 之后有真的浏览器实例,alive 才有意义;现在是老实报「没有把手所以无从判断」还是报 `true`,本篇先按 `true`。
