# Works API

work 树、列、工作单元(现场)、谁在看、轨迹(trace:读写一个接口;agent 的对话也在里面)、痕迹(round,旧路径)、收件箱 / manager。登录后的请求(身份来自 token,见 [auth.md](auth.md)),凡会动某个 work 的(建、改、列上的动作、开 / 重入 / 挪 / 收起 / 关工作单元、打开 work 本身),都算这个人对该 work 的一次心跳(进 `viewers`);进轨迹的动作还把这个人写进段 / 点的 `user.id`(结束段的人是 `memorytalk.end.user.id`)。字段语义见 [`../../structure/v5/work.md`](../../structure/v5/work.md)。

---

## GET /api/works

work 树(森林)。

| 参数 | 说明 |
|---|---|
| `root` | 可选;只返回这个 work 为根的一棵(不存在 → 404) |
| `created_by` | 可选;只看某人建的 |

```json
[
  {"id": "work_…2f2f", "goal": "把 v5 做出来", "created_by": "alice", "parent": null,
   "status": "running", "created_at": "…", "archived_at": null, "viewers": ["alice"],
   "children": [
     {"id": "work_…a1b2", "goal": "实现 issue", "parent": "work_…2f2f", "status": "archived",
      "created_at": "…", "archived_at": "…", "viewers": [], "children": []}
   ]}
]
```

`children` 读时从 `works` 表的 `parent` 拼出来。父不存在的节点当作根。`viewers` = 现在谁在看(见 [users](#get-apiworkswork_idusers))。

## POST /api/works

开工。

```json
{"goal": "实现 work", "parent": "work_…2f2f"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `goal` | 是 | 一句话 |
| `parent` | 否 | 挂到哪个 work 下;不存在 → 404 |

**201** 返回 Work(`status: "running"`,`created_by` = 登录态里的 user,没带则 `null`)。副作用:`works.db` 一个事务里插 work 一行 + 第一列 `c1`(+ 投给管它的 work 的收件箱);开一个 `work` 段;建的人算在看。

## GET /api/works/servers

有哪些 work server 及各自响应的协议。**固定路径,先于 `/{work_id}`。**

```json
[{"name": "bash", "protocols": ["bash"], "description": "…"},
 {"name": "claude", "protocols": ["claude"], "description": "…"},
 {"name": "http", "protocols": ["http", "https"], "description": "…"},
 {"name": "default", "protocols": [], "description": "兜底:没有专门 server 的协议,把协议名当命令名在 tmux 里跑"}]
```

一项 = `memorytalk/backend/work_servers/` 下一个文件。`protocols` 是它自己声明的;`default` 不声明、永远排最后。**寻址在 `POST /api/works/{id}/worklets` 时自动发生**,没有单独的 resolve 端点。

## GET /api/works/{work_id}

返回 Work(带 `viewers`)。带身份 = 打开它,算一次心跳(前端开着页面每 15 秒拉一次)。404 `not_found`。

## PATCH /api/works/{work_id}

```json
{"goal": "…", "status": "archived"}
```

两个字段都可选。`status` 只收 `running` / `archived`,别的值 → 422。规则:

| 目标 | 规则 | 副作用 |
|---|---|---|
| `running` | 无(可从 `archived` 改回) | `archived_at` 清空;从 `archived` 改回 = 新的一段 `work` 段(`links` 指向上一段),现场还活着的工作单元(网页的)也各开新的一段 `worklet` 段 |
| `archived` | 无——**不看子 work**,父子各自归档 | `archived_at`(已归档则保留);**冻结**:先让节点把 agent 的记录推完(`flush`,开着的会话 / 轮次 / 工具段按 `archived` 结束;Codex / Kimi 还是最后收一次 round),再把工作单元现场全部销毁(登记留着);开着的 `worklet` 段和 `work` 段结束(`memorytalk.end.reason = archived`) |

`goal` 变了打一个 `work.renamed` 点(带旧目标);状态变了投给管它的 work 的收件箱。

归档后:`POST …/worklets` → 409(建现场的半中间被归档了也是 409,刚建的现场销毁掉);关掉工作单元不再让节点 flush(归档时做过了),`rounds` 不再从把手同步。

## GET /api/works/{work_id}/trace

轨迹:这个 work 的段和点,OTLP/JSON([designs work-trace.md](../../designs/v5/work-trace.md)),外加 `seq`。**agent 的 output 就是它**:一个工作单元的对话、状态都在这里读,没有单独的 output / messages / state 接口。原来的 `GET …/events` 撤了(404)。

| 参数 | 说明 |
|---|---|
| `subtree` | 可选,默认 `false`;`true` = 连同所有子孙 work |
| `worklet` | 只看这一个工作单元(它的 `worklet` 段和下面的一切) |
| `agent` | 默认 `false`;`1` = 带上 agent 那几层(`agent.session` / `agent.turn` / `agent.tool` 段,`agent.message` / `agent.tool.input` / `agent.tool.output` / `agent.state` 点)。默认只给 `work` / `worklet` 段和人的动作点 |
| `bodies` | 默认 `false`;`1` = 点带正文(`body`:消息原文、工具参数、工具结果) |
| `after` | 变更序号:只要这之后写的或改过的段和点(段开、合并属性、结束都算改) |
| `wait` | 秒,配合 `after`:这次读会读到的东西还没有就挂着,有了或超时(最多 60)才回来。长轮询 |
| `fields` | `cursors` = 只要节点推到哪了(要带 `worklet`;节点重连时用),返回 `{"cursors": [{worklet_id, source, position, updated_at}]}`;`spans` = 只要段、不要点(`logs` 是空的;甘特图 / 火焰图用);别的值 → 422 |

看一个工作单元的对话:`?worklet=<w>&agent=1&bodies=1`,拿回来的 `seq` 下次带成 `&after=<seq>&wait=25`。

```json
{"traces": {"resourceSpans": [{
   "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "memory.talk"}}]},
   "scopeSpans": [{"scope": {"name": "memorytalk.work", "version": "5"}, "spans": [
     {"traceId": "4bf92f3577b34da6a3ce929d0e0e4736", "spanId": "a3ce929d0e0e4736", "name": "work", "kind": 1,
      "startTimeUnixNano": "1790590900000000000",
      "attributes": [{"key": "memorytalk.work.id", "value": {"stringValue": "work_…2f2f"}},
                     {"key": "memorytalk.work.goal", "value": {"stringValue": "把 v5 做出来"}},
                     {"key": "user.id", "value": {"stringValue": "alice"}},
                     {"key": "memorytalk.open", "value": {"boolValue": true}}],
      "links": [], "status": {"code": 0}},
     {"traceId": "4bf9…", "spanId": "00f067aa0ba902b7", "parentSpanId": "a3ce929d0e0e4736", "name": "worklet", "kind": 1,
      "startTimeUnixNano": "1790590931000000000", "endTimeUnixNano": "1790611211000000000",
      "attributes": [{"key": "memorytalk.work.id", "value": {"stringValue": "work_…2f2f"}},
                     {"key": "memorytalk.worklet.id", "value": {"stringValue": "work_…2f2f-w1"}},
                     {"key": "memorytalk.worklet.uri", "value": {"stringValue": "bash:///ws"}},
                     {"key": "memorytalk.worklet.scheme", "value": {"stringValue": "bash"}},
                     {"key": "memorytalk.worklet.server", "value": {"stringValue": "bash"}},
                     {"key": "memorytalk.column.id", "value": {"stringValue": "c3"}},
                     {"key": "memorytalk.column.alias", "value": {"stringValue": "测试"}},
                     {"key": "user.id", "value": {"stringValue": "alice"}},
                     {"key": "memorytalk.end.reason", "value": {"stringValue": "detached"}},
                     {"key": "memorytalk.end.column.id", "value": {"stringValue": "c1"}},
                     {"key": "memorytalk.end.column.alias", "value": {"stringValue": ""}},
                     {"key": "memorytalk.end.user.id", "value": {"stringValue": "bob"}}],
      "links": [], "status": {"code": 1}}]}]}]},
 "logs": {"resourceLogs": [{
   "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "memory.talk"}}]},
   "scopeLogs": [{"scope": {"name": "memorytalk.work", "version": "5"}, "logRecords": [
     {"timeUnixNano": "1790598000000000000", "observedTimeUnixNano": "1790598000000000000", "eventName": "worklet.moved",
      "traceId": "4bf9…", "spanId": "00f067aa0ba902b7",
      "attributes": [{"key": "user.id", "value": {"stringValue": "bob"}},
                     {"key": "memorytalk.worklet.id", "value": {"stringValue": "work_…2f2f-w1"}},
                     {"key": "memorytalk.column.id", "value": {"stringValue": "c1"}},
                     {"key": "memorytalk.column.alias", "value": {"stringValue": ""}},
                     {"key": "memorytalk.index", "value": {"intValue": "1"}},
                     {"key": "memorytalk.from.column.id", "value": {"stringValue": "c3"}},
                     {"key": "memorytalk.from.column.alias", "value": {"stringValue": "测试"}},
                     {"key": "memorytalk.from.index", "value": {"intValue": "0"}}]}]}]}]},
 "seq": "42"}
```

带 `agent=1&bodies=1` 时,agent 的一条消息长这样(`timeUnixNano` 是 agent 记录里的时刻,`observedTimeUnixNano` 是中心收到的时刻):

```json
{"timeUnixNano": "1790598012345000000", "observedTimeUnixNano": "1790598012702000000", "eventName": "agent.message",
 "traceId": "4bf9…", "spanId": "<这一轮的段 id>", "body": {"stringValue": "把配置改成环境变量"},
 "attributes": [{"key": "log.record.uid", "value": {"stringValue": "work_…2f2f-w4:8b1e…"}},
                {"key": "memorytalk.worklet.id", "value": {"stringValue": "work_…2f2f-w4"}},
                {"key": "memorytalk.message.role", "value": {"stringValue": "user"}},
                {"key": "memorytalk.message.kind", "value": {"stringValue": "text"}}]}
```

- 编码按 OTLP/JSON:字段名 lowerCamelCase,id 是十六进制,时间(Unix 纳秒)和 `intValue` 是十进制字符串,`kind` / `status.code` 是整数(1 = OK,0 = Unset,2 = Error——只有出错的工具调用)。
- 段:`work` / `worklet`,带 `agent=1` 再有 `agent.session` / `agent.turn` / `agent.tool`;**开着的段没有 `endTimeUnixNano`**,另带 `memorytalk.open = true`。根段没有 `parentSpanId`;`links` 总在(没有就是空数组),重新打开的 `work` 段指向上一段。段按开始时间(再按 `spanId`)排,点按时间(再按写入先后)排;中心自己写的点 `observedTimeUnixNano` 和 `timeUnixNano` 是同一个值,节点推的不一样。
- `seq`:读的这一刻这几个 work 最大的变更序号(十进制字符串);段的每次开 / 改、点的每次写都取下一个。
- id 由身份算出来,同一份数据再读还是同样的 id:`traceId` 由根 work 算,一棵树一条;`work` / `worklet` 段由「work / worklet + 第几段」算,agent 那几层由节点按会话 / 这一轮人那条输入 / 工具调用 id 算(见 [designs work-trace.md §4](../../designs/v5/work-trace.md))。
- 各段、各点带哪些属性,见 [structure work.md#trace](../../structure/v5/work.md#trace)。读和心跳不进轨迹;收起 / 展开不记。
- work 不存在 → 404;`fields=cursors` 不带 `worklet` → 422。

## POST /api/works/{work_id}/trace

写轨迹:节点把 agent 的记录推上来([designs work-node.md §6](../../designs/v5/work-node.md))。**和 GET 同一个形状**——`traces` + `logs`,外加可选的 `cursors`;GET 出来的文档原样 POST 回去,意思不变。

**只有节点能写**:节点经中心的 unix socket(`<home>/center.sock`,0600)连上来,从那里上来的请求身份就是节点,只能碰 `/api/works/{id}/trace`;登录的人(JWT)POST → 403。

```json
{"traces": {"resourceSpans": [{"scopeSpans": [{"spans": [
    {"traceId": "4bf9…", "spanId": "9c1d7e0b5a2f4c33", "parentSpanId": "<会话段>", "name": "agent.turn", "kind": 1,
     "startTimeUnixNano": "1790598012345000000",
     "attributes": [{"key": "memorytalk.worklet.id", "value": {"stringValue": "work_…2f2f-w4"}}, …], "status": {"code": 0}}]}]}]},
 "logs": {"resourceLogs": [{"scopeLogs": [{"logRecords": [
    {"timeUnixNano": "1790598012345000000", "eventName": "agent.message", "traceId": "4bf9…", "spanId": "9c1d7e0b5a2f4c33",
     "body": {"stringValue": "把配置改成环境变量"},
     "attributes": [{"key": "log.record.uid", "value": {"stringValue": "work_…2f2f-w4:8b1e…"}},
                    {"key": "memorytalk.worklet.id", "value": {"stringValue": "work_…2f2f-w4"}}, …]}]}]}]},
 "cursors": [{"worklet_id": "work_…2f2f-w4", "source": "hooks", "position": "1830"}]}
```

→ **200** `{"spans": {"inserted": 1, "ended": 0, "merged": 0, "ignored": 0}, "points": {"inserted": 1, "duplicate": 0}}`

- **段按 `spanId` 收**:没有就插(没有 `endTimeUnixNano` = 开着);有、还开着,带终点就结束(补终点、status、结束的属性),不带就合并属性(同名以新的为准);已经结束 → `ignored`(结束即定稿)。读出来的 `memorytalk.open` 写回来不算数。
- **点按 `log.record.uid` 收**:有了就 `duplicate`。`observedTimeUnixNano` 由中心填收到的时刻。
- **一次请求一个事务**:段、点、`cursors` 一起写或一起不写。`cursors` 存进 `trace_cursors`(同一个工作单元同一个 `source` 覆盖),用 `GET …/trace?worklet=<w>&fields=cursors` 读回。
- **能写什么**:`agent.session` / `agent.turn` / `agent.tool` 段,`agent.message` / `agent.tool.input` / `agent.tool.output` / `agent.state` 点,以及给 `worklet` 段补一个 `memorytalk.end.reason = gone` 的结束;别的(`work` 段、开 `worklet` 段、别的结束原因、人的动作点)→ 整批 **403**。`gone` 遇上正在关 / 归档 / 重入的,或者现场其实还活着的 → 这一条 `ignored`;收的话中心补上结束那一刻在哪一列。
- **整批 422**:点没有 `log.record.uid`;段 / 点没有 `memorytalk.worklet.id`,或它不是这个 work 的工作单元;`traceId` 不是这棵树的;`spanId` 不是 16 位十六进制;时间不是纳秒;`status.code` 不是 0 / 1 / 2。
- 父段不强求先到;`worklet` 段结束时,里面还开着的 agent 段跟着结束(原因、status 同它,终点取各自最后一次动静)。

## GET /api/works/{work_id}/inbox

收件箱:被 `manager.json` 路由过来的变动——Metas 里这个 work 管的那一片的每次提交,以及子 work(或 `manager` 指过来的 work)的创建 / 状态变化。只追加(`works.db` 的 `inbox` 表)。

```json
[{"ts": "…", "layer": "issue", "path": "memory.talk/配置/该走文件还是环境变量", "subject": "position …#p2: 只用环境变量",
  "sha": "…", "by": "alice", "routed_by": "memory.talk"},
 {"ts": "…", "layer": "work", "path": "work_…child", "subject": "status running -> archived", "sha": null, "by": null, "routed_by": "parent"}]
```

## GET /api/works/{work_id}/manager

这个 work 的变动打给谁:`works.manager` 里的 work,没有则父 work,根 → `null`。

## PUT /api/works/{work_id}/manager

`{"work": "work_…"}` 改写默认;`{"work": null}` 删掉、回到父。返回 `{"work": …}`。

---

## GET /api/works/{work_id}/users

现在谁在看这个 work(按名字排)。只做可见性,不做权限;谁做过什么看 [`/trace`](#get-apiworkswork_idtrace)。

```json
{"current": ["alice", "bob"]}
```

心跳(打开 work、会动它的请求、下面的 `touch`)只在服务进程内存里;超过 120 秒没心跳就不算了;服务重启全部清空。

## POST /api/works/{work_id}/users/touch

心跳:「我在看这个 work」。身份来自登录态。返回同上。

## POST /api/works/{work_id}/users/leave

「我不看了」:立刻从 `current` 里拿掉,不用等超时。前端关页面 / 切走时发。返回同上;本来就不在也没事。

---

## GET /api/works/{work_id}/columns

列清单,从左到右(按 `position`)。

```json
[{"id": "c1", "alias": "调研", "collapsed": false, "position": 0},
 {"id": "c3", "alias": "", "collapsed": true, "position": 1}]
```

**列只承载弱编排**:一个 work 有几列(有序、可起别名、可收起),每个工作单元摆在某一列的某个位置——就这些,没有别的布局对象。工作单元在哪一列、第几个、收没收起,看 [`GET …/worklets`](#get-apiworkswork_idworklets) 里每个工作单元的 `column` / `position` / `collapsed`。

**一列 = 固定编号 + 别名**:`id` 是 `c<编号>`,服务端发、单调递增、永不改不复用(删过列编号就不连续,如上例没有 `c2`);`alias` 是别名,可空可重名,改名只改它(空 = 前端显示「列 <编号>」,起了别名就只显示别名,如「测试」);`collapsed` 整列收起 = 缩成一条窄边;`position` 从左到右 0 起、始终连续。**至少一列**:新 work 就是 `[{"id": "c1", "alias": "", "collapsed": false, "position": 0}]`。列 id 只认 `c<编号>` 这一种写法,别的(包括 `c01`)→ 404。work 不存在 → 404。

**每个动作一个请求**:服务端在当前的列和位置上做(`works.db` 一个事务)、打点,交回动完的样子——列的动作(下面三个)交回列清单,工作单元的挪 / 收起交回工作单元清单。没有版本号,客户端不用带什么(服务端串行,两人各做各的动作都成功),拿交回的清单直接替换本地的。列不建、不删工作单元;但工作单元开的时候就放进一列(`POST …/worklets` 的 `column`,不给 = 最左一列),关掉的从列里拿掉。原来的 `GET` / `PUT …/canvas` 撤了(404)。

## POST /api/works/{work_id}/columns

加一列。

```json
{"alias": "测试", "beside": "c1", "side": "right"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `alias` | 否 | 别名,默认空;最长 80(超长 → 422) |
| `beside` | 否 | 挨着哪一列加;不给 = 加在最右 |
| `side` | 否 | `left` / `right`(默认 `right`),相对 `beside` |

**201** 返回列清单(同 `GET …/columns`,已含新列);新列 id = `c<n>`,`n` 取自 `works.next_column`(取完 +1)。点 `column.added`。`beside` 不存在 → 404。

## PATCH /api/works/{work_id}/columns/{column_id}

```json
{"alias": "测试", "collapsed": true}
```

两个字段都可选。`alias` 改别名(编号不动;首尾空白去掉;空串 = 清掉别名),变了才打点 `column.renamed`(带 `memorytalk.from` = 旧别名);`collapsed` 收起 / 展开整列,不记。返回列清单。列不存在 → 404。

## DELETE /api/works/{work_id}/columns/{column_id}

删一列,返回列清单(右边的列 `position` 往左补),点 `column.removed`。删掉的编号不再发。

| 错误 | 状态 |
|---|---|
| 列不存在 | 404 `not_found` |
| 列里还有工作单元(只有空列能删) | 409 `conflict` |
| 这是最后一列 | 409 `conflict` |

---

## GET /api/works/{work_id}/worklets

```json
[{"id": "work_…-w1", "uri": "codex:///w", "scheme": "codex", "cwd": "/w",
  "created_at": "…", "last_attached": "…",
  "column": "c1", "position": 0, "collapsed": false,
  "alive": true, "window": {"url": "/surface/tmuxd/?arg=work_…-w1", "embed": "/surface/tmuxd/?arg=work_…-w1"},
  "handle": {"kind": "tmux+transcript", "capabilities": ["input.text", "input.keys", "rounds"]}},
 {"id": "work_…-w4", "uri": "bash:///w", "scheme": "bash", "cwd": "/w",
  "created_at": "…", "last_attached": "…",
  "column": "c3", "position": 0, "collapsed": true,
  "alive": false, "window": null, "handle": null}]
```

按开的先后(编号)排,不按位置。每个带摆在哪:`column`(在哪一列,`c<编号>`)、`position`(列里从上数第几个,0 起,同一列里连续)、`collapsed`(收起 = 只剩标题行);不在任何一列的(正常不会有)`column` / `position` 是 `null`,前端摆在最左一列。`alive` 现算(问 server);活着的带 `window` / `handle`,死了的是 `null`。现场自己没了、`worklet` 段还开着的,顺手把段结束成 `gone`(status Unset)。work 不存在 → 404。

## POST /api/works/{work_id}/worklets

在 work 里打开一个块:先验(work 没归档、列存在、URI 有协议;拿协议去 server 那里寻址,声明了的 server,否则 default)→ 取号(`works.next_worklet`)→ 建现场 → 登记工作单元并放进一列(`works.db` 一个事务)→ 开 `worklet` 段 → 交回窗 + 把手,连同它在哪一列第几个。建现场失败则什么都不写、不留登记(号不还);登记那一步失败(列刚好被删了 → 404 `not_found`;work 刚好被归档了 → 409 `conflict`),刚建的现场销毁掉。轨迹写失败只记日志,照样 201。

```json
{"uri": "codex:///w/memory.talk", "column": "c3"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `uri` | 是 | 块即 URI |
| `column` | 否 | 放进哪一列(`c<编号>`)的末尾;不给 = 最左一列。开的时候就定列,不用再挪 |

**201**:

```json
{"id": "work_…-w1", "uri": "codex:///w/memory.talk", "scheme": "codex",
 "cwd": "/w/memory.talk", "created_at": "…", "last_attached": "…",
 "column": "c3", "position": 2, "collapsed": false,
 "alive": true,
 "window": {"url": "/surface/tmuxd/?arg=work_…-w1", "embed": "/surface/tmuxd/?arg=work_…-w1"},
 "handle": {"kind": "tmux+transcript", "capabilities": ["input.text", "input.keys", "rounds"]}}
```

- 由哪个 server 建的不对外——`https://` 走 http server、`vim://` 走 default,调用方不感知。
- `column` / `position`:放进了哪一列、列里第几个(那一列原来有几个,就是第几个)。
- `window.url` 是 tmuxd 自带的 ttyd,挂在主路由 `/surface/tmuxd/?arg=<worklet_id>`(同源相对地址,见 [structure work-server.md](../../structure/v5/work-server.md));http 工作单元是 URL 本身。
- id `<work_id>-w<n>` 在 work 内单调递增、不复用:关掉 `-w1` 再开一个是 `-w2`(计数是 `works.next_worklet`)。
- 副作用:`worklets` 插一行(连同摆在哪);终端类起一个 tmux 会话(名 = 工作单元 id);放进那一列末尾;开一个 `worklet` 段(带 uri / scheme / server 和放进的列)。
- `claude://`:起的是 `claude --session-id <新发的 uuid> --settings <注入 hooks 的文件>`,会话 id 记在登记上(不对外);开起来就让本机节点盯着这个工作单元(节点没起来只记日志,不挡开),它的对话从此由节点推进 trace,`handle.capabilities` 是 `["input.text", "input.keys", "trace.agent"]`。
- `handle.capabilities`:`input.text` / `input.keys` = 能经 [`POST …/input`](#post-apiworkswork_idworkletsworklet_idinput) 往里送字、按键(终端和 agent 都有);`trace.agent` = 它干的事在 trace 里(界面上的「轨迹」;claude 的对话;bash 的每条命令,一条一轮——`bash://<目录>` 起的 bash 带着记命令的钩子,跑脚本的没有);`rounds` = 旧的拉取路径(Codex / Kimi);网页什么都没有。

| 错误 | 状态 |
|---|---|
| work 已归档 | 409 `conflict` |
| `column` 不存在(先验,不建现场、不留登记) | 404 `not_found` |
| 建现场的这会儿列被删了(现场销毁、不留登记) | 404 `not_found` |
| 建现场的这会儿 work 被归档了(现场销毁、不留登记) | 409 `conflict` |
| URI 没协议 | 400 `bad_uri` |
| 要跑的命令不在 PATH(如 `vim://` 走 default 但没装 vim) | 400 `cmd_not_found` |
| tmux 起不来 | 502 `platform` |

## POST /api/works/{work_id}/worklets/{worklet_id}/attach

重入:同一工作单元再次打开,幂等取回同一现场(tmux 会话还在就直接 attach,没了就按原 URI 重建)。返回同上(带它现在在哪一列第几个),`last_attached` 更新。这个工作单元没有开着的 `worklet` 段(现场没了 / 归档后又重新打开)就开新的一段。

| 错误 | 状态 |
|---|---|
| work 已归档(冻住的工作单元不再起现场、不开段;正在归档时点的重入等归档做完,一样 409) | 409 `conflict` |
| 工作单元不存在 | 404 `not_found` |

## DELETE /api/works/{work_id}/worklets/{worklet_id}

关闭即回收:先让节点把这个工作单元的记录读到头、推完,开着的会话 / 轮次 / 工具段按 `detached` 结束(`flush`;Codex / Kimi 还是最后收一次 round;尽力而为,等不到就不等;work 已归档就不做,归档时做过了)→ 销毁现场(tmuxd `session.kill()`)→ 从列里拿掉(同一列下面的往上补)、删登记(一个事务)→ 结束 `worklet` 段(`memorytalk.end.reason = detached`,带结束时所在的列和关它的人;节点没来得及结束的 agent 段跟着结束)。已经没有开着的段(现场没了 / 归档过、重新打开后没重入)就不动段,打一个 `worklet.closed` 点(带当时的列和关它的人)。**200**,`data: null`。

## POST /api/works/{work_id}/worklets/{worklet_id}/input

往现场里送([designs work-server-io.md §4](../../designs/v5/work-server-io.md)):打字,或者按键。

```json
{"kind": "text", "text": "把配置改成环境变量", "submit": true, "force": false}
```

| 字段 | 说明 |
|---|---|
| `kind` | `text`(逐字打进去,可以多行)/ `keys`(按键名)/ `paste`(整段粘进去,现场要有 `input.paste`,现在都还没有) |
| `text` | `text` / `paste` 的内容,最长 64 KiB(超了 → 422) |
| `submit` | 默认 `true`:打完再按一次回车 |
| `keys` | `keys` 用:tmux 键名,`Escape` / `C-c` / `Enter` / `Up` … |
| `force` | agent 正在干活 / 在等确认也照样送;按键默认就是 force(要能发 `Escape` 打断它) |

→ **200** `{"input_id": "3f9c0a1b2c3d4e5f", "state": "idle"}`——`state` 是送的时候 agent 的状态(trace 里最新的 `agent.state`;没有 agent 状态的终端是 `null`)。

- **意思只到「交给现场了」**:字交给 tmux 就返回,不等 agent 接住;接没接住看 trace(它引起的那一轮会出现,带 `memorytalk.input.id`)。
- **门控**:有 `trace.agent` 的按 trace 里最新的 `agent.state`——在 `busy`(agent 正在干活 / bash 有命令在跑)→ 409 `busy`,在 `blocked`(等人确认:这时打的字会被当成回答)→ 409 `blocked`,带 `force` 才送;没有的(default 之类)不门控。
- **留痕不留原文**:每次送在这个工作单元最新的 `worklet` 段上打一个 `worklet.input` 点——`user.id`、`memorytalk.input.id` / `.kind` / `.length` / `.sha256`(去掉首尾空白的 sha256)。节点推来新的一轮时,第一句人的话指纹对得上、前后 60 秒内的,轮次段上记同一个 `memorytalk.input.id`;对不上的就是在终端窗里手打的。
- 现场不在 / work 已归档 → 409 `gone`;这个现场不收这种(网页、bash 的 `paste`)→ 409 `unsupported`;工作单元不存在 → 404。

## POST /api/works/{work_id}/worklets/{worklet_id}/move

挪工作单元:左右挪 = 换列放末尾,上下挪 = 同列换 `index`,一个接口。

```json
{"column": "c1", "index": 0}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `column` | 是 | 挪到哪一列(`c<编号>`) |
| `index` | 否 | 列里从上数第几个(从 0 起,超出按末尾算;负数 → 422);不给 = 末尾 |

返回工作单元清单(同 `GET …/worklets`,挪完的位置都在里面)。`index` 按「先从原列拿掉」之后数,原列下面的往上补、目标列 `≥ index` 的往下让。位置真变了才打点 `worklet.moved`(去哪:`memorytalk.column.*` + `memorytalk.index`;从哪:`memorytalk.from.column.*` + `memorytalk.from.index`)。工作单元不存在或不在任何一列、目标列不存在 → 404。

## PATCH /api/works/{work_id}/worklets/{worklet_id}

`{"collapsed": true}` 收起 / 展开这个工作单元(只剩标题行)。返回工作单元清单,不进轨迹。工作单元不存在或不在任何一列 → 404。

## GET /api/works/{work_id}/worklets/{worklet_id}/rounds

**旧路径,只剩 Codex / Kimi**:它们的记录还是中心去拉,等节点能解析它们就撤掉这个接口。`claude://` 的对话在 trace 里(`GET …/trace?worklet=<w>&agent=1&bodies=1`),这里返回 `[]`。

work 运行中时先从把手同步:按 cwd + 工作单元创建时间定位平台记录文件,新 round 追加进 `worktrace.db` 的 `rounds` 表(按 `id` 去重),有新的就重切一遍 `agent.turn` 段;然后按追加的先后返回全部。

```json
[{"id": "u1", "timestamp": "2026-09-05T10:00:00Z", "role": "human", "text": "把配置改成环境变量"},
 {"id": "a1", "timestamp": "…", "role": "assistant", "text": "好\n[Edit] {\"f\": \"config.py\"}"}]
```

没有 `rounds` 能力的工作单元(bash / http)返回 `[]`(bash)或 `[]`(http)——不报错,因为「没有痕迹」是合法状态。
