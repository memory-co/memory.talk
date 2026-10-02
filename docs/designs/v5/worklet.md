# worklet —— work 里的一个现场(v5 设计)

> **状态:框架稿,已有最简实现。** 本篇只立 worklet 这一层的大框架:它是什么、为什么要从「画布上的块」里独立出来、跟 panel / server / trace 三个邻居怎么分工、一生几步、留下什么。字段见 [`../../structure/v5/work.md`](../../structure/v5/work.md#worklet),端点见 [`../../api/v5/works.md`](../../api/v5/works.md)。

相关:
- v5 work 树(worklet 住在 work 里): [work.md](work.md)
- v5 protocol server(worklet 是 server 建出来的): [work-server.md](work-server.md)
- v5 issue(issue 的出处和证据指向 worklet 留下的消息): [issue.md](metas/issue.md)
- v5 节点(谁读 agent 的会话记录、推进 trace): [work-node.md](work-node.md)
- shellbase 的会话身份(`window` + `block` 位置参数——本篇有意偏离它的那一点): [uri.md §4](https://github.com/memory-co/shellbase/blob/main/docs/v1/works/uri.md)

---

## 1. 一句话:worklet 是 work 里的一个现场

work 是为了做成一件事把现场收拢到一起的容器([work.md §1](work.md));**worklet 就是收进去的每一个现场**——你最初说的「work 里盛放若干个 code agent worklet」,就是它;裸终端和网页也算,只是没有对话:一个跑着 Codex 的工作单元、一个裸终端、一个正在看的网页。它有三样东西:

- **身份**:一个稳定的 id,`<work_id>-w<n>`,在 work 里顺序编号。
- **它是什么**:一个 URI(`codex:///proj`)+ 建它的 server(`codex`)+ 解析出的工作目录。
- **它活没活着**:现场在不在(tmux 会话还在不在)——这不存,每次问 server。

worklet **不是**布局里的一个格子,也**不是**会话记录本身;那两个是它的邻居(§3)。

---

## 2. 为什么要有它:身份必须脱离布局

shellbase 里没有 worklet 这个概念。块的身份写在 URI 的 `window` + `block` 两个位置参数里:同一个 `codex:///proj` 在 `main` 窗口的第 1 格和第 2 格是两个现场,换个格子就换了身份。这在「画布就是全部」的 shellbase 里是对的——块在哪,它就是谁。

v5 的 work 不是画布,画布只是它的视图([work.md §3](work.md)):**布局可以随时重排,重排不改变 work**。这就要求现场的身份**不能挂在格子上**——否则把 Codex 那块从左边拖到右边,后端就认为你关了一个工作单元又开了一个新的,轨迹断成两截,issue 指回来的出处也断了。

所以 v5 把「现场的身份」从块里抽出来,单独立一个对象:**worklet**。它是 v5 原生实现时**唯一有意偏离 shellbase** 的地方([work-server.md §2](work-server.md)):

| | shellbase 的块 | v5 的 worklet |
|---|---|---|
| 身份在哪 | URI 里的 `?window=…&block=…` | 自己的 id,`<work_id>-w<n>` |
| 换个格子 | 换了身份(新现场) | 还是它(布局是视图) |
| 关掉页面 | 现场还在(tmux),下次按同一 URI 重入 | 同,按 worklet id 重入 |
| 谁记着它 | 布局文件里的 panel 记录 | `works.db` 的 `worklets` 表,一个工作单元一行(唯一权威) |

---

## 3. 三个邻居:panel、server、trace

worklet 夹在三个概念中间,分工要清楚:

```
panel(画布上的格子) ──装着──▶ worklet(现场的身份) ──由谁建──▶ server(codex / bash / http / default)
                                      │
                                      └──留下──▶ trace(会话 / 轮次 / 工具段和每条消息,issue 的原料)
```

- **panel 是视图,worklet 是实体**。panel 就是工作单元摆在哪(现在是 `worklets` 那一行上的 `column_number` / `position` / `collapsed`,[work-store.md §4](work-store.md));panel 可以删、可以重排、可以整张画布清空重画,worklet 不动。反过来,worklet 也不要求有 panel——一个工作单元可以暂时没被摆在画布上(比如画布重画时),它还活着。
- **server 建它,work 记它**。server 只回答「这个 id 的现场活没活着、怎么看、怎么驱动」,**不记 work**;worklet 属于哪个 work、什么时候开的、最近什么时候重入,全在 `works.db` 的 `worklets` 表。server 重启后,work 层拿登记去 server 那里把现场一个个取回来([work-server.md §4](work-server.md))。
- **worklet 不是会话记录,会话记录是它留下的痕迹**。v3 的 worklet 是「事后导入的对话记录」;v5 的 worklet 是活的现场,agent 类 worklet 跑着的时候,现场所在机器上的节点读它的会话记录、收 hooks,把会话、轮次、工具调用和每条消息推进 `worktrace.db`([work-node.md](work-node.md)、[work-trace.md §2](work-trace.md))。worklet 是活的现场,trace 是它的痕迹;worklet 销毁了,痕迹留着。

一句话:**panel 是怎么摆,worklet 是它是谁,server 是怎么建,trace 是它留下了什么。** 至于**谁**在操作这个 work,那是 [user.md](user.md) 的事——user 是人,worklet 是现场,两个词别混。

---

## 4. 一生四步:attach → reattach → detach / freeze

1. **attach**(在 work 里打开一个块)。work 层先取号、定下 id(`works.next_worklet`);拿协议去 server 那里寻址;server 用这个 id 幂等地建现场——终端类就是起一个 **tmux 会话,工作单元名 = worklet id**;建起来了才登记并摆上画布(一个事务),开 `worklet` 段,让节点开始盯它(agent 类建现场时就定下会话 id、注入 hooks,[work-node.md §5](work-node.md));交回窗(嵌进画布)和把手(留给 work 层驱动)。建现场失败什么都不写,只是那个号不还,不留半个工作单元([work-store.md §6](work-store.md))。
2. **reattach**(重入)。换设备、刷新页面、服务重启之后,拿 worklet id 再 open 一次:现场还在就直接取回,不在就按原 URI 重建。**同一个 id 永远是同一个现场**——这是 tmux `new -A` 的语义,也是 `*muxd` 规范的 M4。work 已归档就不能重入(409,和 attach 一样),要先把 work 重新打开。
3. **detach**(关闭即回收)。先让节点把它的记录读完、推上来(agent 类,`flush`),再销毁现场 + 删登记,`worklet` 段结束(`detached`)。跟 shellbase 一样,关块不是从画布上摘掉,是真的 kill。
4. **freeze**(work 归档)。work 归档,先让节点把记录推完,所有工作单元的现场销毁、**登记留着**,开着的 `worklet` 段结束(`archived`):工作单元不再活着、不能再 attach,但还能回去看它留下的会话和消息。这是「结束以后工作单元冻结,现场可以回去看但不再是干活的地方」([work.md §6](work.md))在 worklet 上的落法。

detach 和 freeze 的差别:detach 是「这个现场我不要了」,登记一起删;freeze 是「这件事不在这里干了」,登记作为痕迹的索引留下。

---

## 5. 一个 worklet 只属于一个 work,一个确定的节点

- **在 work 里打开的,就是它的**。归属是原生的、在创建那一刻定下的,不靠 cwd 事后推断(v3 explore 的做法)。同一个项目目录可以在不同 work 里各开各的工作单元,互不相干。
- **一个工作单元只属于一个 work,而且是树上一个确定的节点**,不属于「整棵树」。父 work 看不到子 work 的工作单元——它看到的是子 work 的状态。
- **不搬家**。要在别的事里用它的结论,走 issue / card,不把工作单元挪到另一个 work 下。worklet id 里带着 work id,搬家在身份上就说不通。

---

## 6. worklet 留下什么:trace 里的会话和消息,以及 issue 指回来的路

agent 类 worklet(claude / codex / kimi)跑着的时候,现场所在机器上的节点盯着它:开现场时就定下 agent 的会话 id、注入 hooks,所以哪份会话记录是它的不用猜;一有新内容就推进 `worktrace.db`——一个会话一段 `agent.session`,一轮一段 `agent.turn`,一次工具调用一段 `agent.tool`,每条消息一个点,正文在点的 `body` 里([work-node.md](work-node.md)、[work-trace.md §2](work-trace.md))。这是 worklet 对认知层唯一的贡献,也是最重要的:

- **issue 的出处和论证的证据都指向这里**:`origin = {work_id, messages: […]}`,messages 是消息点的 `uid`(`log.record.uid`,由 agent 自己的消息 id 来,稳定,不随追加的先后变)。逐条消息标注、`#问题` 建 issue,全在这份记录上做。
- **只追加**。对话是过程,不是决定;不进 git,也从不改既有的点。
- **bash / http 类 worklet 没有对话**。裸终端没有痕迹(读终端归人:打开那扇窗),网页什么都不留——它们对 work 的意义是「做这件事时打开过什么」,记在登记里、worklet 段上就够了。要不要给终端留命令历史、给网页留访问记录,是 [work.md §8](work.md) 留的那条待定。

---

## 7. 这篇有意不定的事

- **worklet 能不能换 URI**:shellbase 的做法是「改 URI = 销毁重建」。v5 倾向同样——worklet 的 URI 是它身份的一部分,要换就 detach 再 attach 一个新的;但「同一个 agent 工作单元换个工作目录」这种需求真出现了再议。
- **一个 worklet 能不能被多个 panel 装**:同一个 tmux 会话在画布上开两个格子镜像,shellbase 靠完整 URI 显式做到。v5 的 panel 记 `worklet`,技术上允许两个 panel 指同一个工作单元;要不要允许,看协作(多人看同一个 agent)是不是真需求。
  → [work-store.md §4](work-store.md)(已实施)把位置做成 `worklets` 自己的列,一个工作单元只能在一格里;真要镜像再单开表。
- **freeze 之后能不能「解冻」**:work 从归档改回运行中(已允许),工作单元要不要跟着能重新 attach。倾向能——登记还在,reattach 会按原 URI 重建;重建时 agent 可以按原来的会话 id 接回(Claude Code 的 `--resume`),接不回就是新会话,两种在 trace 里都是一段新的 `agent.session`(work-trace.md §2)。
- ~~**记录的同步时机**~~:已定——节点盯着会话记录,一产生就推([work-node.md](work-node.md)),标注流程能实时看到新消息;「逐条消息标注是在 work 运行中做还是归档后再做」不再受同步时机限制。
- **非 tmux 的现场怎么算活着**:http 类 worklet 永远 `alive`,因为没有进程。换成 webmuxd 之后有真的浏览器实例,alive 才有意义;现在是老实报「没有把手所以无从判断」还是报 `true`,本篇先按 `true`。
