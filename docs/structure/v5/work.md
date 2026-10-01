# Work + Canvas + Worklet + Viewers + Round + Trace

做事层的六个对象,存在两个 sqlite 里:`works.db` 管现在(Work / Canvas / Worklet / Viewers / 收件箱),`worktrace.db` 管经过(Trace 的段和点、Round)。机制见 [`../../designs/v5/work.md`](../../designs/v5/work.md),存储见 [`../../designs/v5/work-store.md`](../../designs/v5/work-store.md)。

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
- 进入 `archived` 即**冻结**:所有工作单元的现场销毁、登记留着、不能再 attach;`rounds` 不再从把手同步,只读已记的。
- 可以从 `archived` 改回 `running`(取消归档)。
- 写入只收 `running` / `archived`,别的值 `422`。
- 没有自动归档——由人或 agent 标。

**读视图 `WorkNode`** = Work + `children: WorkNode[]`(读时拼出来,不存)。

## Canvas

work 的画布:**几列,每列从上到下摆工作单元**,每个工作单元可收起。**至少一列**,新 work 就有一列 `c1`。**只是视图**——重排不改变 work 的工作单元和目的。没有整份写口:加列 / 改别名 / 删列 / 挪 / 收起各是一个请求,服务端在当前画布上做(见 [api works.md](../../api/v5/works.md#get-apiworkswork_idcanvas)、[designs work-events.md](../../designs/v5/work-events.md))。

```json
{
  "version": 3,
  "next_column": 4,
  "columns": [
    {"id": "c1", "alias": "调研", "panels": [{"worklet": "work_2026…2f2f-w1", "collapsed": false}, {"worklet": "work_2026…2f2f-w2", "collapsed": true}], "collapsed": false},
    {"id": "c3", "alias": "", "panels": [{"worklet": "work_2026…2f2f-w4", "collapsed": false}], "collapsed": true}
  ]
}
```

| 字段 | 说明 |
|---|---|
| `version` | 每个动作成功后 +1(工作单元开 / 关时服务端改画布也 +1);客户端不用带,只拿它判断缓存旧没旧 |
| `next_column` | 下一列的编号;加列时发 `c<next_column>` 再 +1,单调递增 |
| `columns[].id` | `c<编号>`:列的身份,**服务端发,永不改、不复用**(删过列编号就不连续);端点、事件、CLI 一律用它 |
| `columns[].alias` | 别名,可空(默认)、可重名,最长 80;改名只改它。前端显示 `列 <编号>` / `列 <编号> · <别名>`,**不按位置叫「第 n 列」** |
| `columns[].panels[]` | 这一列从上到下的格子 |
| `columns[].collapsed` | 整列收起 = 缩成一条窄边;列只有空了才能删,最后一列不能删 |
| `panels[].worklet` | 装的是哪个工作单元;一个工作单元最多出现在一个格子里 |
| `panels[].collapsed` | 收起 = 只剩标题行 |

**跟 shellbase 唯一有意不同的地方**:格子的身份不在 `(window, block)` 位置参数里,而在 `worklet`——把工作单元挪到别的列,工作单元不变。开出来的工作单元进指定列末尾(不指定 = 最左一列),关掉的自动从格子里拿掉;画布里没提到的工作单元前端补在第一列。

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

**读视图 `WorkletView`** = Worklet + `alive`(问 server 现算)+ `window` / `handle`(attach / reattach 时返回;list 时活着的也带,死了的是 `null`)。

一个工作单元只属于一个 work、一个确定节点。要在别的事里用它的结论,走 issue / card,不搬工作单元。

## Viewers(users)

**人**,不是现场。现在谁在看这个 work;只做可见性,**不做权限**(整个实例给一个团队用)。机制见 [`../../designs/v5/user.md`](../../designs/v5/user.md) §3。

- 存在 `works.viewers`(名字数组,按名字排),对外是 `Work.viewers`;**只记现在**,由服务进程内存里的心跳表(work → 人 → 最后一次心跳)整份算出来再写。
- 心跳:建 work、打开 work(`GET /works/{id}`)、带身份的会动这个 work 的请求、`POST /works/{id}/users/touch`;超过 120 秒没心跳清出去;`POST /works/{id}/users/leave` 立刻拿掉;服务重启全部清空。
- **读视图 `WorkUsers`**:`{"current": ["alice", "bob"]}`。

不再有「谁动过」的名单:谁做过什么看 [Trace](#trace) 里每个段、每个点的 `user.id`。不带身份的请求照样能操作,只是不记名、不算在看。

## Round

agent 工作单元的工作单元痕迹:从各平台的记录文件读出来、只追加进 `worktrace.db` 的 `rounds` 表(按 `(worklet_id, round_id)` 去重,按追加的先后读)。

```json
{"id": "8b1e…", "timestamp": "2026-09-05T23:05:12Z", "role": "human", "text": "把配置改成环境变量"}
```

| 字段 | 说明 |
|---|---|
| `id` | 平台自己的消息 id(Claude Code 的 `uuid`、Kimi 的事件 `uuid`;Codex 用 `<文件名>:<行号>`);同步时按它去重 |
| `timestamp` | 平台原样透传(可能为空、格式异构:Claude Code / Codex 是 ISO 串,Kimi 是 Unix 秒;**不要拿它排序**,文件顺序就是时间顺序)。切 `agent.turn` 时才统一成 Unix 纳秒 |
| `role` | `human` / `assistant` / `tool` / `system` |
| `text` | 扁平化文本:工具调用写成 `[Name] args`,结果写成 `[result] …`,思考写成 `[thinking] …` |

只记这四项——round 是 issue 的原料(逐 round 标注、`#问题`),不是检索单元。

## Trace

work 的经过:有起止的记成**段**(span),一个时刻的事记成**点**(log record),字段和 OTel 一对一,存在 `worktrace.db` 的 `spans` / `points` 表;`GET /works/{id}/trace` 拼成 OTLP/JSON(`{"traces": TracesData, "logs": LogsData}`,见 [api works.md](../../api/v5/works.md#get-apiworkswork_idtrace))。机制见 [designs work-trace.md](../../designs/v5/work-trace.md)。

- **trace id** = `sha256("memorytalk/trace/" + 根 work id)` 前 16 字节:一棵 work 树一条 trace。
- **span id**:`work` 段 = `sha256("memorytalk/span/work/<work id>/<第几段>")` 前 8 字节(第几段 = 这个 work 已有几段,第一段是 0;重新打开一次多一段);`worklet` 段同理用 worklet id(`memorytalk/span/worklet/…`);`agent.turn` = `sha256("memorytalk/span/turn/<worklet id>/<这一轮第一条 round 的 id>")` 前 8 字节,同一轮再同步一次还是同一个 id(`spans.first_round_id` 存这条 round 的 id)。
- 父子:子 work 的 `work` 段挂在父 work 最新的 `work` 段下,`worklet` 段挂在它 work 最新的 `work` 段下,`agent.turn` 挂在它工作单元最新的 `worklet` 段下。
- 时间是 Unix 纳秒(对外是十进制字符串);开着的段没有 `endTimeUnixNano`,另带 `memorytalk.open = true`。`kind` 都是 1(INTERNAL);`status.code` 开着时 0,正常结束 1(OK),`gone` 保持 0(Unset;跟着它结束的 `agent.turn` 也是 0)。

| 段 `name` | 开 | 结束 | 属性(`user.id` = 开它的人;结束时另记 `memorytalk.end.reason` 和 `memorytalk.end.user.id`——`gone` 没有人,不记) |
|---|---|---|---|
| `work` | 建 work;重新打开(新的一段,`links` 指向上一段,`memorytalk.work.reopened = true`) | 归档(`archived`) | `memorytalk.work.id`、`memorytalk.work.goal` |
| `worklet` | 打开工作单元;重入时没有开着的段才开新的一段;work 重新打开时现场还活着的(网页的)也开新的一段 | 关掉(`detached`)、归档(`archived`)、现场没了(`gone`,status Unset) | `memorytalk.work.id`、`memorytalk.worklet.id` / `.uri`(原样)/ `.scheme` / `.server`、`memorytalk.column.id` / `.alias`(开的时候在哪一列);结束时 `memorytalk.end.column.id` / `.alias` |
| `agent.turn` | 同步 round 时切出来:人的一条输入起 | 下一条人的输入之前的最后一条 round;没有就开着,worklet 段结束时跟着结束 | `memorytalk.worklet.id`、`memorytalk.round.first` / `.last` / `.count`、`gen_ai.system`;**不记人** |

| 点 `eventName` | 挂在 | 属性(除 `user.id` 外) |
|---|---|---|
| `work.renamed` | `work` 段 | `memorytalk.work.goal`、`memorytalk.from`(旧目标) |
| `column.added` / `column.removed` | `work` 段 | `memorytalk.column.id` / `.alias` |
| `column.renamed` | `work` 段 | `memorytalk.column.id` / `.alias`(新别名)、`memorytalk.from`(旧别名);只有别名真变了才记 |
| `worklet.moved` | 这个工作单元最新的 `worklet` 段 | `memorytalk.worklet.id`、`memorytalk.column.id` / `.alias` + `memorytalk.index`(去哪)、`memorytalk.from.column.id` / `.alias` + `memorytalk.from.index`(从哪);位置没变不记 |
| `worklet.closed` | 这个工作单元最新的 `worklet` 段 | `memorytalk.worklet.id`、`memorytalk.column.id` / `.alias`(关的时候在哪一列);关掉时已经没有开着的段才记(现场没了 / 归档过、重新打开后没重入),段不再动 |

**列标记**:`memorytalk.column.id` 是身份(`c<n>`),`.alias` 是当时的别名快照,后来改名不回改。收起 / 展开(列或工作单元)、读、心跳**不记**。收件箱和 round 的正文不进轨迹。

## 存储

| 库 | 表 | 主键 | 列 |
|---|---|---|---|
| `works.db` | `works` | `id` | `parent`(索引)、`goal`、`status`、`created_by`(索引)、`created_at`、`archived_at`、`manager`、`viewers`(JSON 数组)、`next_worklet`、`next_column`、`canvas_version` |
| | `work_columns` | (`work_id`, `number`) | `alias`、`collapsed`、`position`;索引 (`work_id`, `position`) |
| | `worklets` | `id` | `work_id`(索引)、`number`、`uri`、`scheme`、`server`、`cwd`、`created_at`、`last_attached`、`column_number`(空 = 没摆上画布)、`position`、`collapsed`;索引 (`work_id`, `column_number`, `position`) |
| | `inbox` | `seq` | `work_id`(索引,空 = 没人管)、`ts`、`layer`、`path`、`subject`、`sha`、`by`、`routed_by` |
| `worktrace.db` | `spans` | `span_id` | `trace_id` / `work_id` / `worklet_id` / `user_id` / `end_user_id`(都有索引)、`parent_span_id`、`name`、`kind`、`start_time_unix_nano`、`end_time_unix_nano`(空 = 开着)、`status_code`、`attributes` / `links`(OTLP JSON)、`first_round_id`(`agent.turn`) |
| | `points` | `seq` | `trace_id`、`span_id`(索引)、`work_id`(索引)、`worklet_id`、`column_number`、`user_id`(索引)、`event_name`(索引)、`time_unix_nano`、`attributes` |
| | `rounds` | `seq` | `work_id`、`worklet_id`(索引)、`round_id`、`timestamp`、`role`、`text` |

画布没有自己的表:`GET /works/{id}/canvas` 由 `work_columns`(按 `position`)和 `worklets` 的位置列(按 `column_number, position`)拼出来。一个动作在 `works.db` 里一个事务,然后写 `worktrace.db`;轨迹写失败不回滚 work。读写纪律:单写者(服务进程)、无缓存直读。**不进 git**——work 记的是过程,git 记的是决定(见 [`../../designs/v5/metas/store.md`](../../designs/v5/metas/store.md) §4)。
