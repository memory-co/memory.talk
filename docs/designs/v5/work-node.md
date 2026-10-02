# work-node —— 节点:现场和采集住在边上,往中心推(v5 设计)

> **状态:部分实施——Claude Code 已经走这条路**(§11 第 2 ~ 5 步里 Claude 的部分:写入口和 `trace_cursors`、节点 v0(`memorytalk/node/`,`memory.talk node`)、`--session-id` 定身份、hooks、前端等变化)。Codex / Kimi 还是中心去拉;tmuxd 还在中心;远程节点没做。本篇定 agent 的记录(以后还有现场本身)怎么从「中心去拉」改成「边上往中心推」:**每台机器一个节点进程**,读本机 agent 的会话记录、收 agent 的 hooks、看现场活没活,把这些变成 trace 推给中心;**中心只管存、查和做决定**。推上来的是什么(会话 / 轮次 / 工具段,消息点)见 [work-trace.md §2](work-trace.md),落在哪几张表见 [structure worktrace.md](../../structure/v5/worktrace.md)。

相关:
- server 怎么把现场建出来(窗 + 把手): [work-server.md](work-server.md)
- 每个 server 的 input / output 口子(output 就是本篇推上来的东西): [work-server-io.md](work-server-io.md)
- trace 的段、点、id: [work-trace.md](work-trace.md)
- 两个库(`works.db` 管现在、`worktrace.db` 管经过): [work-store.md](work-store.md)

---

## 1. 为什么:现在是中心去拉

agent 的记录现在这样进 trace:有人打开「对话记录」(前端每 4 秒拉一次),或者关掉 / 归档之前,中心才去读会话记录——按 cwd + 修改时间**猜**哪份会话记录是这个工作单元的,**整份**读进来,和库里**全部**已有的记录比一遍去重,再把这个工作单元的记录**整个**重切一遍轮次。问题出在方向上:

1. **读的人驱动写。** 没人看,数据就不进 trace;几个人同时看,同样的活做几遍;读接口有写的副作用。
2. **身份靠猜。** 开现场那一刻 server 什么都知道(工作目录、命令,甚至可以指定 agent 的会话 id),却把这些丢了,事后用「同目录 + 最新修改」去猜。同一目录开两个 Claude,或者人自己在那个目录里跑着 Claude,就会读到同一份。
3. **中心在干边上的活。** 每家 agent 的记录格式、一轮怎么切、什么算在等确认——这些知识写在中心(`WorkService._sync`、`turns.py`),格式一变(Codex 已经变过一次)就得改中心。
4. **全量重做。** 每次同步都整份重读、整体重切,会话越长越慢。
5. **边界靠近似。** 一轮要等到下一条人的输入才算结束;可三家的记录里其实都有明确的收尾标记(Claude Code 的 `stop_reason`、Codex 的 `task_complete` / `turn_aborted`、Kimi 的 `turn.ended` / `turn.cancel`),没用上。
6. **没人负责盯着活着的现场。** 服务重启后没人接着看;「现场没了」只在有人列清单时顺带发现。

## 2. 两个选择:谁来驱动,推的东西放在哪

| 选择 | 定了 | 解决什么 |
|---|---|---|
| 谁驱动 | 拉(有人读才触发)→ **推(数据一产生就触发)** | 实时:状态是新的,input 的门控(work-server-io.md §5)才靠得住;没人看也有数据 |
| 放在哪 | 中心进程里 → **中心之外,现场所在的机器上** | 减负、隔离、能跨机器 |

实时靠的是推(事件驱动),不一定要出进程;出进程靠的是下面四条,按分量排:

1. **数据在哪,读的人就得在哪。** 会话记录、hooks 都落在 agent 跑的那台机器上;以后现场在别的机器(work-server.md §8 的「远程现场」),中心根本读不到那些文件。
2. **中心保持通用。** 各家 agent 的格式和规则放在边上,中心只存只查、不认识任何 agent;格式变了改节点,不动中心。
3. **故障隔离。** 一个卡死的解析、一份几百 MB 的记录,只拖住边上,不拖住登录、work、元认知。
4. **负载。** 这条现在最弱:改成增量读之后,解析量对中心微不足道。现在的重是「每次全量重读」这个写法造成的,放哪都得改。

## 3. 中心和节点各管什么

| | 中心(管控 + 存储 + 界面) | 节点(数据面,每台机器一个) |
|---|---|---|
| 存 | `works.db`、`worktrace.db` | 只有一份 hooks 事件的本地落盘(§5),不存 trace |
| 决定 | 开 / 关 / 归档 / 重入、谁能做、登记 | 不做决定,照中心说的盯 / 停 |
| 权威 | 登记(有哪些工作单元)、人、**推到哪了**(§6) | **现场活没活着、agent 说了什么** |
| 认识 agent 吗 | 不认识:只收段和点 | 认识:格式、一轮怎么切、什么算在等确认 |
| 对外 | API、界面;trace 的读和写是同一个接口(§6、§9) | 只对中心 |

现在 tmuxd 和 ttyd 在中心进程里;第一步节点只做上报,现场还是中心建(§11)。

## 4. 节点长什么样

- **按机器,不按工作单元。** 一台机器一个节点进程,里面每个活着的工作单元一个**上报任务**(进程里的任务,不是进程)。凭证、连接、日志、升级、看护都只有一份;tmux server、ttyd 本来就是一台机器一份,以后搬进节点也顺。
- **不包着 agent。** agent 照旧由 tmux 起,上报任务在旁边读文件、收 hooks。节点升级或重启不用杀 agent;反过来 agent 退出也不影响节点。
- **上报任务做什么**,看 server 的能力(work-server-io.md §2):

  | 工作单元 | 读什么 | 推什么 |
  |---|---|---|
  | agent(claude / codex / kimi) | 会话记录(只读新增的部分:先 stat,大小或修改时间变了才读)、hooks 事件文件、tmux 会话在不在 | 会话 / 轮次 / 工具段,消息点,状态点;现场没了就报 `gone` |
  | 终端(bash / default) | tmux 会话在不在 | 现场没了就报 `gone`(带最后确认活着的时刻) |
  | http | — | 没有(等 webmuxd) |

- **一个后台循环轮着看所有工作单元**,不是一个工作单元一个线程;只 stat,变了才读。
- **格式漂移要看得见。** 解析器遇到不认识的记录类型就计数,记在会话段上(`memorytalk.unrecognized`),格式变了是一条看得见的数据,不是悄悄丢掉(Codex 那次就是悄悄丢的)。

## 5. 身份在开现场时定

| agent | 怎么定 | 现状 |
|---|---|---|
| Claude Code | 起的时候带 `--session-id <uuid>`(中心发);会话记录就是 `~/.claude/projects/*/<uuid>.jsonl`,按文件名找,不用管目录名怎么编码。再用 `--settings` 注入 hooks:`SessionStart`(换会话时报新的会话 id 和记录路径)、`UserPromptSubmit` / `Stop`(一轮的起止)、`Notification`(在等人确认) | 两个参数本机已确认 |
| Codex | 能按 id 接回(`resume`);新开时能不能指定 id 待查。退路:**认领后钉住**——开现场后第一份新出现的、cwd 对得上的记录认作自己的,把它的会话 id 记下来,以后只读这一份 | 待查 |
| Kimi | 能按 id 接回(`-S/--session <id>`);新开能否指定待查;退路同上 | 待查 |

- **一个工作单元一生可以有几个会话**(Claude Code 里 `/clear` 就换一个),所以「钉住」钉的是起点,之后跟着 `SessionStart` 换;每个会话在 trace 里是一段 `agent.session`(work-trace.md §2)。
- 开的时候定的会话 id 记在登记上(`works.db` 的 `worklets` 加一列),重入、节点重连时拿它对。
- **hooks 不走网络。** hook 命令只把事件追加到这个工作单元在节点状态目录里的事件文件(`<节点目录>/worklets/<id>/hooks.jsonl`),上报任务连同会话记录一起读。不用发 token,agent 的环境里没有任何凭证。

## 6. 推:写 trace 的接口就是读它的那个

```
GET  /api/works/{work_id}/trace     读:{"traces": TracesData, "logs": LogsData}(work-trace.md §6)
POST /api/works/{work_id}/trace     写:同一个形状,多一栏可选的 "cursors"
```

节点推上来的就是 OTLP/JSON:段放在 `traces.resourceSpans` 里,点放在 `logs.resourceLogs` 里,和 `GET` 读出来的一个样:

```json
{"traces": {"resourceSpans": [{"resource": {…}, "scopeSpans": [{"scope": {…}, "spans": [
    {"traceId": "…", "spanId": "…", "parentSpanId": "…", "name": "agent.turn", "kind": 1,
     "startTimeUnixNano": "…", "attributes": [{"key": "memorytalk.worklet.id", "value": {"stringValue": "…-w4"}}, …],
     "status": {"code": 0}}]}]}]},
 "logs":   {"resourceLogs": [{"resource": {…}, "scopeLogs": [{"scope": {…}, "logRecords": [
    {"timeUnixNano": "…", "eventName": "agent.message", "traceId": "…", "spanId": "…",
     "body": {"stringValue": "…"}, "attributes": [{"key": "log.record.uid", "value": {"stringValue": "…"}}, …]}]}]}]},
 "cursors": [{"worklet_id": "…-w4", "source": "<会话 id 或 hooks>", "position": "…"}]}
→ 200 {"spans": {"inserted": 3, "ended": 1, "merged": 0, "ignored": 0}, "points": {"inserted": 12, "duplicate": 0}}
```

- **读写一个形状,一条写路径。** `GET` 出去的文档原样 `POST` 回来,意思不变;中心解析 OTLP/JSON 的代码只有一份。中心自己的动作(人建 work、开工作单元、挪列……)也走同一个写入函数,只是不经过 HTTP——`worktrace.db` 只有一条写路径,两边的规则不会分叉。
- **段怎么收**(按 `spanId`;开着还是结束,只看有没有 `endTimeUnixNano`,和读的时候一样):
  - 库里没有 → 插进去;没有终点就是开着(读的时候它带 `memorytalk.open = true`,写的时候不用带)。
  - 库里有、还开着,收到的带终点 → 补上终点、status 和结束的属性(同名以新的为准);两处同时结束,先到的算数。
  - 库里有、还开着,收到的也开着 → 只合并属性(比如这一轮的消息数在涨)。
  - 库里有、已经结束 → 跳过。**结束即定稿。**
- **点怎么收**:按 `log.record.uid` 插,有了就跳过;节点推的点必须带 uid,没有就 422。`observedTimeUnixNano` 由中心填收到的时刻,请求里带的不算。
- **一次请求一个事务**:段、点和 `cursors` 一起提交或一起不提交。所以投递只要「至少一次」:没收到回应就整批重推,重复的被跳过。
- **能写什么有边界**:节点只能写它负责的工作单元的 `agent.*` 段和点(`agent.message` / `agent.tool.*` / `agent.state`),以及给 `worklet` 段补一个 `gone` 结束;`work` / `worklet` 段的开、其余的结束、动作点,都只由中心自己写。超出边界整批 403;记录里的 `memorytalk.worklet.id` 不属于路径上这个 work 的,422。路径上只有一个 work,所以一个节点手里几个 work 的记录分几次请求推。
- **父段不强求先到**:乱序也收;读的时候找不到父的段,先挂在它的工作单元下面。
- **推到哪了,中心说了算。** `cursors` 和数据在同一个事务里存进 `trace_cursors` 表;节点连上(或重连)时用 `GET /api/works/{id}/trace?worklet=…&fields=cursors` 读回来,从那里接着读、接着推。**会话记录本身就是缓冲**:中心停多久,节点就停多久,回来一条不丢,节点不用自己攒队列。只有 hooks 事件不在会话记录里,所以先落本地文件,推成功了再往前挪。
- **鉴权**:节点经本机 unix socket 连中心,用的是同一套 API,从 socket 上来的请求身份就是节点;登录的人(JWT)能 `GET`、不能 `POST`。跨机器的节点以后用节点 token(§8)。
- **为什么不直接用 OTLP/HTTP 的 `/v1/traces` + `/v1/logs`**:那是两个端点、两次请求,段和点进不了一个事务,也没处放游标;标准 OTLP 里也没有「开着的段」。所以用同样的编码、一个请求装两种信号,和 `GET` 对称;往外导出时仍是标准 OTLP(work-trace.md §8)。

## 7. 控制:中心 → 节点

| 中心说 | 节点做 |
|---|---|
| `watch(worklet, server, cwd, 会话 id, since)` | 起一个上报任务;先问游标,接着读 |
| `flush(worklet, reason)` | 读到文件末尾、推完,把这个工作单元开着的 `agent.*` 段按 `reason` 结束,停掉任务,回一句「完了」 |
| `list()` | 报自己在盯哪些工作单元、本机还活着的 tmux 会话 |
| (现场搬进节点以后)`open` / `close` / `input` | 建 / 销毁现场、往里送字 |

- **关掉和归档**:中心先 `flush`,等节点「完了」(超时就不等,迟到的点照收,段不重开),再销毁现场、结束 worklet 段。这样子段一定先于父段结束。
- **重连对账**:节点连上时报 `list()`,中心拿登记对一遍——登记了、现场活着、节点没在盯 → 让它 `watch`;登记了、现场没了 → 结束成 `gone`;现场活着、没登记 → 孤儿,收掉。work-trace.md §5 一直没做的「启动时对一遍」就是这个。

## 8. 凭证

- **同一台机器**:两个方向都走 unix socket(0600,属于跑服务的那个用户),靠文件权限,不发 token。
- **跨机器**(以后):节点注册时领一个节点级 token,只能往它负责的工作单元推。
- agent 的环境里**不放任何凭证**;hooks 只碰本地文件。

## 9. 实时到浏览器

边上推到中心只是一半。前端现在每 4~5 秒整份拉一次;改成**同一个 trace 接口**的 `after` + `wait`([work-trace.md §6](work-trace.md)):带上次读到的变更序号去等,有变化(新消息、轮次开始或结束、状态变了)就返回,没有就挂着,超时再来。不另开 `/stream` 一类的推送接口;以后真要 SSE,也只是同一个资源换一种返回方式(`Accept: text/event-stream`)。

## 10. 代价

- **多一个进程**:安装、升级、版本不一致都要管。`memory.talk server start` 把两个一起起;接收口带版本号,老节点照样能推。
- **排查变成两处**:界面上要能看到节点在不在、最后一次心跳。
- **前期代码比放在进程里多**:所以分步(§11)。

## 11. 分步(每一步都能单独上线)

1. **修格式、用真实记录做测试样例**:Claude 的目录名编码、Codex 的新格式、Kimi 的 `cwd` 和毫秒;从本机真实会话里截一段脱敏做 fixture。跟架构无关,先做。
2. **中心开写入口 + 节点 v0**:`POST /api/works/{id}/trace`(和读同一个形状)和 `trace_cursors` 表;节点只做上报,本机进程,跟 `server start` 一起起;去掉中心「去拉」的那些路径(`_sync`、`turns.py`、`rounds` 表)。tmuxd 先留在中心。
3. **开现场时定身份**:Claude 用 `--session-id`;Codex / Kimi 先认领后钉住。
4. **Claude hooks** 写事件文件:轮次的起止、在等确认、换会话。
5. **前端改成等变化**:`GET …/trace` 的 `after` + `wait`,不再每几秒整份拉。
6. **tmuxd / ttyd 搬进节点**,窗不再经过中心进程——到这一步,重启中心才不会断终端(现在窗是中心进程里的代理)。
7. **远程节点**。

## 12. 这篇有意不定的事

- **节点和中心怎么一起跑**:现在是两个进程、节点不做中心的子进程——`server start` 两个都起,`server stop` 两个都停,`server restart` 只重启中心;中心连不上时节点等着(游标不动),回来了接着推。要不要改成中心看护的子进程,用一阵再看。
- **tmuxd 搬进节点以后,窗怎么到浏览器**:中心代理到节点的 ttyd socket,还是浏览器直连节点。
- **远程节点**:注册、token、网络断开时怎么报。
- **agent 自己的 OTel 遥测**:Claude Code 能直接推 OTLP(token、成本、API 调用),要不要由节点收进来补在轮次上。
- **子 agent、`/resume` 的细节**:见 work-trace.md §10。
