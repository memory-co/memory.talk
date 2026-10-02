# Work + Column + Worklet + Viewers + Trace

做事层的五个对象,存在两个 sqlite 里:`works.db` 管现在(Work / Column / Worklet / Viewers / 收件箱),`worktrace.db` 管经过(Trace:段和点,agent 的每条消息也是点)。机制见 [`../../designs/v5/work.md`](../../designs/v5/work.md),存储见 [`../../designs/v5/work-store.md`](../../designs/v5/work-store.md)。

## Work

树上一个节点。

```json
{
  "id": "work_202609052302072f2f",
  "goal": "把 v5 做出来",
  "created_by": "alice",
  "parent": null,
  "status": "running",
  "created_at": "2026-09-05T23:02:07Z",
  "archived_at": null,
  "viewers": ["alice"]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `work_<时间戳><4hex>`,自动 |
| `goal` | string | 它是什么事(一句话) |
| `created_by` | string \| null | 谁建的(归属,建时定下不改;**不是权限**,见 [designs user.md](../../designs/v5/user.md)) |
| `parent` | string \| null | 属于哪件更大的事;`null` = 根。**work 之间只有这一种直接关系**——没有 project 之类的分组字段,横向关系靠 issue |
| `status` | `running` \| `archived` | 三层里只有 work 有状态;新建即 `running` |
| `created_at` | ISO 8601 | |
| `archived_at` | ISO 8601 \| null | 进入 `archived` 时写(已是 `archived` 则保留);回到 `running` 清空 |
| `viewers` | string[] | 现在谁在看(心跳算出来的,按名字排;重启清空),见 [Viewers](#viewersusers);只读 |

**状态规则**:
- 只有两档:`running`(还在这里干活)/ `archived`(不再在这里干活——做成了还是放下了,对系统没有区别)。
- 归档**不看子 work**:父子各归各的,没有「子 work 全完才能归档」的约束。
- 进入 `archived` 即**冻结**:所有工作单元的现场销毁、登记留着、不能再 attach;agent 的记录在归档前由节点推完,之后不再追加。
- 可以从 `archived` 改回 `running`(取消归档)。
- 写入只收 `running` / `archived`,别的值 `422`。
- 没有自动归档——由人或 agent 标。

**读视图 `WorkNode`** = Work + `children: WorkNode[]`(读时拼出来,不存)。

## Column

work 的一列。**列只承载弱编排**:一个 work 有几列(有序、可起别名、可收起),每个工作单元摆在某一列的某个位置(记在 [Worklet](#worklet) 自己的 `column` / `position` / `collapsed` 上)——就这些,没有别的布局对象。**至少一列**,新 work 就有一列 `c1`。挪动、重排不改变 work 的工作单元和目的。加列 / 改别名 / 删列 / 挪 / 收起各是一个请求,服务端在当前的列和位置上做(见 [api works.md](../../api/v5/works.md#get-apiworkswork_idcolumns)、[designs work-events.md](../../designs/v5/work-events.md))。

```json
[
  {"id": "c1", "alias": "调研", "collapsed": false, "position": 0},
  {"id": "c3", "alias": "", "collapsed": true, "position": 1}
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `c<编号>`:列的身份,**服务端发(`works.next_column`),单调递增、永不改、不复用**(删过列编号就不连续,如上例没有 `c2`);只认这一种写法(`c01` 也不算,→ 404);端点、轨迹、CLI 一律用它 |
| `alias` | string | 别名,可空(默认)、可重名,最长 80;改名只改它。前端有别名就只显示别名(`测试`),没有显示 `列 <编号>`,**不按位置叫「第 n 列」** |
| `collapsed` | bool | 整列收起 = 缩成一条窄边 |
| `position` | int | 从左到右第几列,0 起,同一个 work 里始终连续;清单按它排 |

列只有空了才能删,最后一列不能删。读视图就是**列清单**(`GET /works/{id}/columns`,按 `position`);列的动作交回动完的列清单。

## Worklet

work 的一个工作单元 = 一个现场。**在 work 里打开就是它的**,归属原生,不靠 cwd 推断。

```json
{
  "id": "work_202609052302072f2f-w1",
  "uri": "codex:///home/me/memory.talk",
  "scheme": "codex",
  "cwd": "/home/me/memory.talk",
  "created_at": "2026-09-05T23:02:10Z",
  "last_attached": "2026-09-05T23:40:01Z"
}
```

| 字段 | 说明 |
|---|---|
| `id` | `<work_id>-w<n>`,work 内**单调递增、不复用**(关掉 `-w1` 再开一个是 `-w2`;计数是 `works.next_worklet`,建现场失败这个号也不还);**就是 tmux 会话名**(终端类) |
| `uri` | 打开它用的 URI(原样) |
| `scheme` | URI 的协议 |
| (`server`) | 建它的 server 名,**只在登记(`worklets` 表)里、不对外**——销毁 / 取把手时内部用(`https` → `http`,`vim` → `default`,调用方不感知) |
| `cwd` | server 解析出的工作目录(终端类);浏览器类为 `null` |
| `created_at` | 工作单元诞生时刻;agent 类 server 用它找「之后新出现的那份会话记录」 |
| `last_attached` | 最近一次重入 |

**读视图 `WorkletView`** = Worklet + 摆在哪(`column` / `position` / `collapsed`)+ `alive`(问 server 现算)+ `window` / `handle`(attach / reattach 时返回;list 时活着的也带,死了的是 `null`)。

```json
{
  "id": "work_202609052302072f2f-w1",
  "uri": "codex:///home/me/memory.talk",
  "scheme": "codex",
  "cwd": "/home/me/memory.talk",
  "created_at": "2026-09-05T23:02:10Z",
  "last_attached": "2026-09-05T23:40:01Z",
  "column": "c3",
  "position": 0,
  "collapsed": false,
  "alive": true,
  "window": {"url": "/surface/tmuxd/?arg=work_202609052302072f2f-w1", "embed": "/surface/tmuxd/?arg=work_202609052302072f2f-w1"},
  "handle": {"kind": "tmux+transcript", "capabilities": ["input.text", "input.keys", "input.paste", "output.messages", "state"]}
}
```

| 字段 | 说明 |
|---|---|
| `column` | 在哪一列(`c<编号>`,见 [Column](#column));不在任何一列 = `null`(正常流程不会有:打开就放进一列,关掉连行一起删;前端把它摆在最左一列) |
| `position` | 列里从上数第几个,0 起,同一列里始终连续;`column` 为 `null` 时也是 `null` |
| `collapsed` | 收起 = 只剩标题行;收起 / 展开不进轨迹 |
| `alive` | 现场活没活着,每次问 server |
| `window` / `handle` | 窗 + 把手([work-server.md](work-server.md));死了的是 `null` |

**位置不是身份**——跟 shellbase 唯一有意不同的地方:shellbase 的块身份在 `(window, block)` 位置参数里,这里工作单元的身份是 `id`,把它挪到别的列、换个位置,工作单元不变。开出来的工作单元进指定列末尾(不指定 = 最左一列,即 `position` 为 0 的那列),关掉的从列里拿掉、下面的往上补;一个工作单元只在一个位置。清单按开的先后(编号)排,不按位置;挪 / 收起交回整份工作单元清单。

一个工作单元只属于一个 work、一个确定节点。要在别的事里用它的结论,走 issue / card,不搬工作单元。

## Viewers(users)

**人**,不是现场。现在谁在看这个 work;只做可见性,**不做权限**(整个实例给一个团队用)。机制见 [`../../designs/v5/user.md`](../../designs/v5/user.md) §3。

- 存在 `works.viewers`(名字数组,按名字排),对外是 `Work.viewers`;**只记现在**,由服务进程内存里的心跳表(work → 人 → 最后一次心跳)整份算出来再写。
- 心跳:建 work、打开 work(`GET /works/{id}`)、带身份的会动这个 work 的请求、`POST /works/{id}/users/touch`;超过 120 秒没心跳清出去;`POST /works/{id}/users/leave` 立刻拿掉;服务重启全部清空。
- **读视图 `WorkUsers`**:`{"current": ["alice", "bob"]}`。

不再有「谁动过」的名单:谁做过什么看 [Trace](#trace) 里每个段、每个点的 `user.id`。不带身份的请求照样能操作,只是不记名、不算在看。

## 消息

agent 对话里的一条:人的输入、助手的回复、工具调用的参数和结果。**不是单独的对象,是 [Trace](#trace) 里的一个点**——由节点从 agent 的会话记录读出来推上来([designs work-node.md](../../designs/v5/work-node.md)),正文在点的 `body` 里;它属于哪一轮、哪次工具调用,看它挂在哪一段。逐列见 [worktrace.md](worktrace.md)。

看一个工作单元的对话(`GET /works/{id}/worklets/{w}/messages`,按游标往后读),一条长这样:

```json
{"uid": "work_2026…2f2f-w4:8b1e…", "kind": "agent.message", "role": "user", "time_unix_nano": "1790598012345000000",
 "session": "<会话段 id>", "turn": "<轮次段 id>", "tool": null, "seq": 1042, "body": "把配置改成环境变量"}
```

| 字段 | 说明 |
|---|---|
| `uid` | 稳定的身份:`<worklet id>:<来源里的消息 id>`(Claude Code 的 `uuid`、Codex 的 `<rollout 文件名>:<行号>`、Kimi 的事件 `uuid`;一条记录里有几块内容时再加 `:<第几块>`)。推重复了按它去重;认知层引用一条消息也用它 |
| `kind` | `agent.message`(说的话、思考)/ `agent.tool.input`(工具调用的参数)/ `agent.tool.output`(工具的结果) |
| `role` | `user` / `assistant` / `system`;工具的参数和结果不带 |
| `time_unix_nano` | 记录里的时刻(节点按各家格式换算好,对外是十进制字符串) |
| `session` / `turn` / `tool` | 它所在的会话段、轮次段、工具段的 id;没有的为 `null` |
| `seq` | 中心写入的先后,读的游标 |
| `body` | 正文:消息的文字、工具的参数(JSON 文本)或结果 |

消息是 issue 的原料(逐条消息标注、`#问题`),不是检索单元。

## Trace

work 的经过:有起止的记成**段**(span),一个时刻的事记成**点**(log record),字段和 OTel 一对一,存在 `worktrace.db` 的 `spans` / `points` 表(逐列的表设计见 [worktrace.md](worktrace.md))。读写同一个路径、同一个形状:`GET /works/{id}/trace` 拼成 OTLP/JSON(`{"traces": TracesData, "logs": LogsData}`),节点用 `POST /works/{id}/trace` 推同一个形状。机制见 [designs work-trace.md](../../designs/v5/work-trace.md)、[work-node.md](../../designs/v5/work-node.md)。

- **trace id** = `sha256("memorytalk/trace/" + 根 work id)` 前 16 字节:一棵 work 树一条 trace。
- **span id** 由身份算,取 sha256 前 8 字节:`work` = `memorytalk/span/work/<work id>/<第几段>`(第几段 = 这个 work 已有几段,第一段是 0;重新打开一次多一段);`worklet` 同理用 worklet id;`agent.session` = `…/session/<worklet id>/<会话 id>/<这一段第一条记录的 uid>`;`agent.turn` = `…/turn/<worklet id>/<这一轮人那条输入的 uid>`;`agent.tool` = `…/tool/<worklet id>/<调用 id>`。前两种中心算,后三种节点算。
- 父子:子 work 的 `work` 段挂在父 work 最新的 `work` 段下;`worklet` 段挂在它 work 最新的 `work` 段下;`agent.session` 挂在它工作单元最新的 `worklet` 段下;`agent.turn` 挂在会话段下;`agent.tool` 挂在轮次段下。
- 时间是 Unix 纳秒(对外是十进制字符串);开着的段没有 `endTimeUnixNano`,另带 `memorytalk.open = true`。`kind` 都是 1(INTERNAL);`status.code` 开着时 0,正常结束 1(OK),`gone` 保持 0(Unset;跟着它结束的子段也是 0),结果出错的工具调用 2(Error)。**结束即定稿。**

| 段 `name` | 谁写 | 开 | 结束 | 属性(`user.id` = 开它的人;结束时另记 `memorytalk.end.reason` 和 `memorytalk.end.user.id`——`gone` 和 `agent.*` 没有人,不记) |
|---|---|---|---|---|
| `work` | 中心 | 建 work;重新打开(新的一段,`links` 指向上一段,`memorytalk.work.reopened = true`) | 归档(`archived`) | `memorytalk.work.id`、`memorytalk.work.goal` |
| `worklet` | 中心(`gone` 由节点报) | 打开工作单元;重入时没有开着的段才开新的一段;work 重新打开时现场还活着的(网页的)也开新的一段 | 关掉(`detached`)、归档(`archived`)、现场没了(`gone`,status Unset) | `memorytalk.work.id`、`memorytalk.worklet.id` / `.uri`(原样)/ `.scheme` / `.server`、`memorytalk.column.id` / `.alias`(开的时候在哪一列);结束时 `memorytalk.end.column.id` / `.alias` |
| `agent.session` | 节点 | agent 开始一个会话(新开、`/resume` 接回、`/clear` 之后的新会话) | 被下一个会话接替(`replaced`),或跟着 worklet 段 | `memorytalk.worklet.id`、`gen_ai.conversation.id`、`memorytalk.session.source`、`gen_ai.system`、`memorytalk.unrecognized` |
| `agent.turn` | 节点 | 人的一条输入 | agent 收尾(`completed`)、被打断(`cancelled`),或跟着会话 / worklet 段 | `memorytalk.worklet.id`、`gen_ai.operation.name`、`gen_ai.usage.input_tokens` / `.output_tokens`、`memorytalk.message.count`、`memorytalk.input.id`(从 API 送进来的那句) |
| `agent.tool` | 节点 | 一次工具调用 | 拿到结果(出错 status 2);轮次先结束了就跟着(`cancelled`) | `memorytalk.worklet.id`、`gen_ai.operation.name`、`gen_ai.tool.name`、`gen_ai.tool.call.id` |

动作点(中心写,人做动作的那一刻):

| 点 `eventName` | 挂在 | 属性(除 `user.id` 外) |
|---|---|---|
| `work.renamed` | `work` 段 | `memorytalk.work.goal`、`memorytalk.from`(旧目标) |
| `column.added` / `column.removed` | `work` 段 | `memorytalk.column.id` / `.alias` |
| `column.renamed` | `work` 段 | `memorytalk.column.id` / `.alias`(新别名)、`memorytalk.from`(旧别名);只有别名真变了才记 |
| `worklet.moved` | 这个工作单元最新的 `worklet` 段 | `memorytalk.worklet.id`、`memorytalk.column.id` / `.alias` + `memorytalk.index`(去哪)、`memorytalk.from.column.id` / `.alias` + `memorytalk.from.index`(从哪);位置没变不记 |
| `worklet.closed` | 这个工作单元最新的 `worklet` 段 | `memorytalk.worklet.id`、`memorytalk.column.id` / `.alias`(关的时候在哪一列);关掉时已经没有开着的段才记(现场没了 / 归档过、重新打开后没重入),段不再动 |
| `worklet.input` | 这个工作单元最新的 `worklet` 段 | `memorytalk.input.id` / `.kind` / `.length` / `.sha256`;不存原文 |

agent 点(节点写;都带 `log.record.uid`,正文在 `body`,见 [消息](#消息)):

| 点 `eventName` | 挂在 | 属性 |
|---|---|---|
| `agent.message` | 所在轮次段(第一条人的输入之前的挂会话段) | `memorytalk.message.role`(`user` / `assistant` / `system`)、`memorytalk.message.kind`(`text` / `thinking`) |
| `agent.tool.input` / `agent.tool.output` | 那次调用的工具段 | `gen_ai.tool.name`、`gen_ai.tool.call.id`;结果出错时 `memorytalk.tool.error` |
| `agent.state` | 会话段 | `memorytalk.state`(`idle` / `busy` / `blocked`);没有正文 |

**列标记**:`memorytalk.column.id` 是身份(`c<n>`),`.alias` 是当时的别名快照,后来改名不回改。收起 / 展开(列或工作单元)、读、心跳**不记**。收件箱不进轨迹。

## 存储

| 库 | 表 | 主键 | 列 |
|---|---|---|---|
| `works.db` | `works` | `id` | `parent`(索引)、`goal`、`status`、`created_by`(索引)、`created_at`、`archived_at`、`manager`、`viewers`(JSON 数组)、`next_worklet`、`next_column` |
| | `work_columns` | (`work_id`, `number`) | `alias`、`collapsed`、`position`;索引 (`work_id`, `position`) |
| | `worklets` | `id` | `work_id`(索引)、`number`、`uri`、`scheme`、`server`、`cwd`、`created_at`、`last_attached`、`column_number`(空 = 不在任何一列)、`position`、`collapsed`;索引 (`work_id`, `column_number`, `position`) |
| | `inbox` | `seq` | `work_id`(索引,空 = 没人管)、`ts`、`layer`、`path`、`subject`、`sha`、`by`、`routed_by` |
| `worktrace.db` | `spans` | `span_id` | `trace_id` / `work_id` / `worklet_id` / `user_id` / `end_user_id`(都有索引)、`parent_span_id`、`name`、`kind`、`start_time_unix_nano`、`end_time_unix_nano`(空 = 开着)、`status_code`、`attributes` / `links`(OTLP JSON) |
| | `points` | `seq` | `uid`(唯一)、`trace_id`、`span_id`(索引)、`work_id`(索引)、`worklet_id`(和 `seq` 一起索引)、`column_number`、`user_id`(索引)、`event_name`(索引)、`time_unix_nano`、`observed_time_unix_nano`、`body`、`attributes` |
| | `trace_cursors` | (`worklet_id`, `source`) | `position`、`updated_at` |

列清单(`GET /works/{id}/columns`)就是 `work_columns` 按 `position` 读;工作单元在哪一列第几个就是 `worklets` 自己的 `column_number` / `position` / `collapsed`,随工作单元清单(`GET /works/{id}/worklets`)一起出去,不另拼一份布局。一个动作在 `works.db` 里一个事务,然后写 `worktrace.db`;轨迹写失败不回滚 work。读写纪律:单写者(服务进程)、无缓存直读。**不进 git**——work 记的是过程,git 记的是决定(见 [`../../designs/v5/metas/store.md`](../../designs/v5/metas/store.md) §4)。
