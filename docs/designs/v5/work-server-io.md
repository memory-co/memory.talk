# work-server-io —— 每个 work server 一对口子:input 各自实现,output 走 trace(v5 设计)

> **状态:设计稿,未实施。** 本篇回答两件事:「每个 server 一个 input 口、一个 output 口;output 复用 trace 链路往上送,input 由各 server 自己实现(比如 claude 用 tmuxd 的 `send` 把字符串打进去)」这个模型够不够;不够的地方补什么。字段落地后进 [`../../structure/v5/work.md`](../../structure/v5/work.md),端点进 [`../../api/v5/works.md`](../../api/v5/works.md)。

相关:
- server 是什么、把手是什么(`send` 在把手上有、API 不露,§8 留的门就是本篇): [work-server.md](work-server.md)
- trace:段、点、`rounds` 表、`agent.turn` 怎么切: [work-trace.md](work-trace.md)
- 工作单元的身份、一生: [worklet.md](worklet.md)
- tmuxd 只写不读(读终端归人): [work-server.md §6](work-server.md)

---

## 1. 模型一句话

```
              input(各 server 自己实现)                         output(统一走 trace)
 调用方 ──▶ POST …/input ──▶ server.input() ──▶ 现场            现场 ──▶ server 的读取器 ──▶ worktrace.db ──▶ 调用方
            (人、CLI、别的 agent)    claude: tmuxd send               (agent 的会话记录文件)   rounds / agent.turn / 点     GET …/output · …/trace
```

**input 归 server**:往现场里送东西,每种现场的「送法」不一样(终端打字、浏览器点按钮),只有 server 知道。
**output 归 trace**:现场吐出来的东西,统一落进 `worktrace.db`,所有读的人走同一条路,不各开一条。

**结论先说:方向是对的,但只有这两句还不完整。** 按 §8 的清单逐条过,缺下面五样,本篇逐一补上:

1. **output 现在是「有人读才拉」,不是口子**。round 只在有人 `GET …/rounds`、或关掉 / 归档前才同步进 trace;没人看,输出就不往上走。要有一个**泵**(§3.1)。
2. **input 要能知道「现在能不能送」**。往一个正在跑的 Claude Code 里打字,会插进它这一轮;要有**状态**(空闲 / 忙 / 等人确认),而现在的 `agent.turn` 要到下一条人的输入才结束,判断不了「这一轮完了没有」(§5)。
3. **input 自己也要进 trace,并且和它引起的那一轮连上**。不然只看得到「agent 跑了一轮」,看不到「是谁、从哪送进来的哪句话触发的」(§4.3)。
4. **input 不只一种形状**。一句话、按一个键(Esc、Ctrl-C)、一段多行文字,在终端里是三件事;多行要用粘贴,tmuxd 现在没有(§4.2)。
5. **不是每个 server 都有 output**。bash / default 背后是 tmuxd,**只写不读**;http 现在连把手都没有。口子要能声明「我没有」(§6)。

---

## 2. 两个口子的契约

每个 server 的**把手**上多两样能力,并且在 `HandleInfo.capabilities` 里如实声明(状态不撒谎,`*muxd` M13):

| 能力 | 意思 | 谁有(第一版) |
|---|---|---|
| `input.text` | 打一行字,可选再按回车提交 | bash、default、claude、codex、kimi |
| `input.keys` | 按键名:`Enter` / `Escape` / `C-c` / `Up` … | 同上 |
| `input.paste` | 一段多行文字原样进去,不被当成多次回车 | claude、codex、kimi(要 tmuxd 加 `paste`,§4.2) |
| `output.rounds` | 现场吐出来的内容按 round 进 trace | claude、codex、kimi |
| `state` | 现在是空闲 / 忙 / 等人确认 / 不在了 | claude、codex、kimi(§5);终端类只有「在 / 不在」 |

http 第一版什么都没有(换成 webmuxd 后有 CDP:点击、填表、读 DOM)。**调用方先看能力再用**,没有的能力调了就是 `409 unsupported`,不假装成功。

---

## 3. output:复用 trace

### 3.1 「复用 trace」具体是哪几张表

trace 里已经有 output 需要的全部落脚处,不新开表:

| output 的什么 | 落在 trace 的哪 | 已有 / 要补 |
|---|---|---|
| 内容(说了什么、调了什么工具、结果) | `rounds` 表,一条 round 一行,只追加 | 已有 |
| 结构(一轮从哪到哪) | `agent.turn` 段,引用 `round.first` / `.last` | 已有,结束条件要补(§5) |
| 状态变化(开始忙了、在等确认、空闲了) | worklet 段上的点 `worklet.state` | 要补 |
| 现场没了 | worklet 段结束,`end.reason = gone` | 已有 |

**缺的是泵。** 现在 `rounds()` 是被动的:谁调 `GET …/rounds`,才去读一次会话记录文件、把新 round 写进 trace。作为口子,要反过来:

- **每个开着的、有 `output.rounds` 的工作单元有一个读取器**,在后台盯它的会话记录文件(按 mtime 轮询,1 秒;能用 inotify 就用),一有新内容就切成 round、写进 `rounds`、重切 `agent.turn`、更新状态。
- 读取器是**服务进程里的后台任务**,跟着 worklet 段走:段开就起,段结束(关掉 / 归档 / `gone`)前最后读一次就停。服务重启时,对着 `spans` 表里开着的 worklet 段把读取器都拉起来(和 work-trace.md §5「服务启动时对一遍」是同一件事,一起做)。
- `GET …/rounds` 从此**只读库,不再触发同步**。读和写分开,读的人多少不影响现场。

### 3.2 怎么往外读

trace 已经是给人看的(`GET …/trace`、右侧「动态」)。output 口给的是**程序**,要的是「从上次读到的地方接着读,没有新的就等一会儿」:

```
GET /works/{id}/worklets/{w}/output?after=<cursor>&wait=30
→ {"rounds": [...], "state": "idle", "cursor": "<新游标>"}
```

- `cursor` 是 `rounds` 表里这个工作单元的行序号(只追加,单调),不透明地交给调用方。
- `wait` 秒内没有新 round 也没有状态变化,就返回空列表和原游标(长轮询)。第一版不做 SSE / WebSocket:长轮询对 CLI、脚本、别的 agent 都最好接,将来要推再加。
- 一次最多返回 200 条;还有更多,调用方带新游标再来。

这和 `GET …/trace` 不冲突:trace 给整件事的结构,output 给一个工作单元的内容流。底下是同一份数据。

---

## 4. input:各 server 自己实现

### 4.1 契约

```python
class Input(BaseModel):
    kind: Literal["text", "keys", "paste"]
    text: str = ""            # text / paste
    submit: bool = True       # text / paste 之后要不要再按一次回车
    keys: list[str] = []      # keys:tmux 键名

handle.input(inp: Input) -> None     # 交给现场就返回;不等它处理完,也不保证它收下了
```

**语义只到「交给现场了」**——tmuxd 的 `send` 就是这个意思:字符交给 tmux 就返回,不是「命令跑完了」,也不是「agent 接住了」。「接住了没有」要看 output(§4.3)。

### 4.2 各 server 怎么送

| server | text | keys | paste | 备注 |
|---|---|---|---|---|
| bash / default | `session.send(text, enter=submit)` | `session.send_key(*keys)` | 不提供 | 多行在 shell 里就是多条命令,本来就该一行行送 |
| claude | 同上 | 同上 | `session.paste(text)` 再按回车 | 逐字送的换行在 TUI 里可能被当成回车提交,第一行就先发出去了(要实测);括号粘贴让它认出「这是一整段」,不受影响 |
| codex / kimi | 同上 | 同上 | 同上 | 同 claude,各自的 TUI 怎么处理粘贴要逐个验 |
| http | — | — | — | 等 webmuxd |

所以「各 server 自己实现」落到代码上,差别其实不大:终端这一族共用 `TmuxHandle.input()`(text / keys),agent 三个再加 `paste`。真正各不相同的是 §5 的**状态**,不是送法。

**tmuxd 要补一个 `paste`。** 现在只有 `send`(`send-keys -l`,一个换行就是一次回车)和 `send_key`。加 `Session.paste(text)`:`load-buffer` 一个只给这次用的 buffer,再 `paste-buffer -p -d`(`-p` = 括号粘贴,TUI 能认出「这是一整段粘进来的」;`-d` = 用完删 buffer)。这是 tmuxd 的事,一个小版本。

### 4.3 input 也进 trace,并且连上它引起的那一轮

每次 input 在这个工作单元最新的 worklet 段上打一个点:

| 点 | 属性 |
|---|---|
| `worklet.input` | `user.id`、`memorytalk.input.id`(服务端发)、`memorytalk.input.kind`、`memorytalk.input.length`、`memorytalk.input.sha256` |

**默认不存原文**。往 bash 里送的可能是密码、token;agent 那边原文本来就会作为人的 round 出现在 `rounds` 里,不用再存一份。

**连上那一轮**:读取器切出一个新的 `agent.turn`,它的第一条人的 round 如果和最近 60 秒内某个 `worklet.input` 对得上(原文的 sha256 一样;粘贴的去掉首尾空白再比),就在这个 turn 段上记 `memorytalk.input.id`,再加一条 link 指向那个点所在的段。这样从 trace 里就能读出:**bob 在 10:02 从 CLI 送进去的这句话,引起了 agent 这一轮,跑了 3 分钟、调了 12 次工具**。对不上的(人直接在终端窗里打的),turn 上就没有这个属性——这本身也是信息:这一轮是在窗里手打的。

---

## 5. 状态:input 要知道现在能不能送

agent 的现场有三种需要区分的状态,`state` 能力报出来:

| 状态 | 意思 | 这时送 input 会怎样 |
|---|---|---|
| `idle` | 上一轮结束了,在等人说话 | 正常 |
| `busy` | 正在跑一轮 | 打的字会插进去,或者被排进它的输入队列(各 CLI 不一样) |
| `blocked` | 停下来等人确认(要不要允许这个命令、要不要改这个文件) | 打的字会被当成对确认框的回答——最危险 |
| `gone` | 现场不在了 | 送不进去 |

**`POST …/input` 默认只在 `idle` 时送**,其余返回 `409 busy` / `409 blocked` / `409 gone`,带当前状态;调用方明确要插话就带 `force: true`(比如要发 `Escape` 打断它——发键的时候默认就是 force)。

**状态从哪来**,第一版和以后分两步:

1. **从会话记录推**(第一版):读取器读到最后一条记录是 agent 这一轮的收尾(Claude Code:assistant 消息 `stop_reason` 为 `end_turn`;Codex:`task_complete`;Kimi 对应的结束事件)→ `idle`;读到人的输入之后还没收尾 → `busy`;读到一个工具调用在等批准 → `blocked`。每个 adapter 多实现一个 `state(records)`。这同时补上 work-trace.md 的一个缺口:**`agent.turn` 可以在收尾那一刻结束**,不用等到下一条人的输入。
2. **agent 自己报**(以后):Claude Code 有 hooks(`Stop`、`Notification`),起现场时把一个指向 memory.talk 的 hook 写进它的设置,它自己就会在停下、等确认的那一刻通知过来。比从文件推更准、更及时;代价是要给每种 agent 配,先不做。

终端类(bash / default)没有可信的「忙不忙」——tmuxd 只写不读,也不该去猜屏幕。它们的 `state` 只有 `idle`(在)和 `gone`(不在),input 不做门控,调用方自己负责。

---

## 6. 没有 output 的 server

bash / default 是 tmuxd 起的,**tmuxd 只写不读**:读终端归人(打开那扇窗)。这条不为本篇破例。所以它们**没有 `output.rounds`**,output 口对它们返回 `409 unsupported`。

想过、没选的:

- **`tmux pipe-pane` 把终端原始输出写到文件,当 output**。拿到的是带转义序列的字节流,不是内容:进度条、光标移动、全屏程序(vim、htop)都是噪声,也没有「一轮」可言。要做也是另一种能力(`output.raw`),不混进 rounds。先不做。
- **抓屏(`capture-pane`)**。tmuxd 刻意不提供,`capture` 早就去掉了(work-server.md §6)。

http 现在没有把手;等它换成 webmuxd,input 是 CDP 的点击 / 输入,output 是页面事件,到时再按本篇的契约接进来。

---

## 7. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/works/{id}/worklets/{w}/input` | `{kind, text?, submit?, keys?, force?}`;成功返回 `{input_id, state}`。work 已归档 / 现场不在 → 409;能力不支持 → 409 `unsupported`;状态不对且没 `force` → 409 `busy` / `blocked`;`text` 最长 64 KiB |
| `GET` | `/api/works/{id}/worklets/{w}/output` | `?after=&wait=`(§3.2) |
| `GET` | `/api/works/{id}/worklets/{w}/state` | `{state, since}`;worklets 清单里也带一份 |

`HandleInfo.capabilities` 改成 §2 那几个名字(现在的 `send` / `rounds` 换成 `input.*` / `output.rounds`)。

CLI:

```
memory.talk work send <work_id> <worklet_id> "<text>" [--no-submit] [--paste] [--force]
memory.talk work key  <work_id> <worklet_id> Escape [C-c …]
memory.talk work tail <work_id> <worklet_id> [--follow]       # 长轮询 output,一条 round 一段
```

权限:跟界面一样——登录的人都能送,送了记 `user.id`。不另加一层「谁能驱动谁的 agent」,这和 work 层「只做可见性、不做权限」一致([user.md](user.md));真要分,和 auth 一起定。

---

## 8. 完整性清单

按「一个口子要回答的问题」逐条过:

| 问题 | 原来的模型 | 本篇 |
|---|---|---|
| 谁有这个口子? | 「每个 server 都有」 | 能力声明,没有就明说没有(§2、§6) |
| output 什么时候产生? | 复用 trace | 后台读取器持续泵进 trace,不靠有人来读(§3.1) |
| output 怎么被程序读? | — | 游标 + 长轮询(§3.2) |
| input 有几种? | 送字符串 | text / keys / paste(§4.1、§4.2) |
| input 成功是什么意思? | — | 只到「交给现场」;接没接住看 output(§4.1) |
| 现在能不能送? | — | 状态 + 默认只在 idle 时送(§5) |
| input 留不留痕? | — | `worklet.input` 点,不存原文(§4.3) |
| input 和它引起的输出连得上吗? | — | turn 段带 `input.id` + link(§4.3) |
| 一轮什么时候结束? | 下一条人的输入之前 | agent 收尾那一刻(§5,顺带修 work-trace) |
| 现场不在、work 归档了? | — | 409,状态报 `gone`(§5、§7) |
| 人在窗里手打,和 API 同时送? | — | 都进同一个现场、同一份记录;对不上 `input.id` 的就是手打的(§4.3) |
| 谁能送? | — | 登录的人,记 `user.id`(§7) |

---

## 9. 这篇有意不定的事

- **agent 驱动 agent**。有了 input 和 output,「A 的输出喂给 B」就是一个循环;要不要由 memory.talk 来编排(而不只是开口子),以及怎么防住两个 agent 互相喂个没完,是另一篇的事。本篇只保证每一跳都在 trace 里看得见、带 `input.id` 连得上。
- **input 原文存不存**。默认不存(§4.3);如果审计要求「每句送进去的话都可查」,再加一个按 work 打开的开关。
- **状态改成 agent 自己报**(§5 第 2 步):先做 Claude Code 的 hooks,其他 agent 看各自有没有类似机制。
- **终端的原始输出**(`output.raw`,§6):有真实需求再做。
- **远程 server**:口子的契约是本地 Python 把手;server 跑到别的机器上时,input / output 怎么过去,和 work-server.md §8 的「远程现场」一起定。
