# Works API

work 树、画布、工作单元(现场)、谁在看、痕迹(round)、轨迹(trace)、收件箱 / manager。登录后的请求(身份来自 token,见 [auth.md](auth.md)),凡会动某个 work 的(建、改、画布上的每个动作、开 / 重入 / 关工作单元、打开 work 本身),都算这个人对该 work 的一次心跳(进 `viewers`);进轨迹的动作还把这个人写进段 / 点的 `user.id`(结束段的人是 `memorytalk.end.user.id`)。字段语义见 [`../../structure/v5/work.md`](../../structure/v5/work.md)。

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
| `archived` | 无——**不看子 work**,父子各自归档 | `archived_at`(已归档则保留);**冻结**:先最后收一次 round,再把工作单元现场全部销毁(登记留着);开着的 `worklet` 段和 `work` 段结束(`memorytalk.end.reason = archived`) |

`goal` 变了打一个 `work.renamed` 点(带旧目标);状态变了投给管它的 work 的收件箱。

归档后:`POST …/worklets` → 409(建现场的半中间被归档了也是 409,刚建的现场销毁掉);`rounds` 不再从把手同步,关掉工作单元也不再收。

## GET /api/works/{work_id}/trace

轨迹:这个 work 的段和点,OTLP/JSON([designs work-trace.md](../../designs/v5/work-trace.md))。原来的 `GET …/events` 撤了(404)。

| 参数 | 说明 |
|---|---|
| `subtree` | 可选,默认 `false`;`true` = 连同所有子孙 work |

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
                     {"key": "memorytalk.from.index", "value": {"intValue": "0"}}]}]}]}]}}
```

- 编码按 OTLP/JSON:字段名 lowerCamelCase,id 是十六进制,时间(Unix 纳秒)和 `intValue` 是十进制字符串,`kind` / `status.code` 是整数(1 = OK,0 = Unset)。
- 段:`work` / `worklet` / `agent.turn`;**开着的段没有 `endTimeUnixNano`**,另带 `memorytalk.open = true`。根段没有 `parentSpanId`;`links` 总在(没有就是空数组),重新打开的 `work` 段指向上一段。段按开始时间(再按 `spanId`)排,点按写入先后排;点的 `observedTimeUnixNano` 和 `timeUnixNano` 是同一个值。
- id 由身份算出来,同一份数据再读还是同样的 id:`traceId` 由根 work 算,一棵树一条;段 id 由「work / worklet + 第几段」或「worklet + 这一轮第一条 round」算(见 [designs work-trace.md §4](../../designs/v5/work-trace.md))。
- 各段、各点带哪些属性,见 [structure work.md#trace](../../structure/v5/work.md#trace)。读和心跳不进轨迹;收起 / 展开不记。
- work 不存在 → 404。

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

## GET /api/works/{work_id}/canvas

```json
{"version": 3, "next_column": 4,
 "columns": [{"id": "c1", "alias": "调研", "panels": [{"worklet": "work_…-w1", "collapsed": false}, {"worklet": "work_…-w2", "collapsed": true}], "collapsed": false},
             {"id": "c3", "alias": "", "panels": [{"worklet": "work_…-w4", "collapsed": false}], "collapsed": true}]}
```

布局 = 几列,每列从上到下摆工作单元;工作单元可收起(只剩标题行),整列也可收起(缩成一条窄边)。**一列 = 固定编号 + 别名**:`id` 是 `c<编号>`,服务端发、单调递增、永不改不复用(删过列编号就不连续,如上例没有 `c2`);`alias` 是别名,可空可重名,改名只改它(空 = 前端显示「列 <编号>」,否则「列 <编号> · <别名>」)。**至少一列**:新 work 的画布就是 `{"version": 0, "next_column": 2, "columns": [{"id": "c1", …}]}`。列 id 只认 `c<编号>` 这一种写法,别的(包括 `c01`)→ 404。

**画布没有整份写口**(`PUT …/canvas` 已撤,→ 405):每个动作一个请求,服务端在当前画布上做(`works.db` 一个事务)、`version + 1`、打点,返回新画布。不需要客户端带 `version`(服务端串行,两人各做各的动作都成功);`version` 只用来判断本地缓存旧没旧。**画布是视图**——它不建、不删工作单元;但跟着工作单元走:`POST …/worklets` 开出来的工作单元进指定列末尾,`DELETE` 掉的自动从格子里拿掉,这两处也 `version + 1`。

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

**201** 返回新画布;新列 id = `c<next_column>`,`next_column + 1`。点 `column.added`。`beside` 不存在 → 404。

## PATCH /api/works/{work_id}/columns/{column_id}

```json
{"alias": "测试", "collapsed": true}
```

两个字段都可选。`alias` 改别名(编号不动;首尾空白去掉;空串 = 清掉别名),变了才打点 `column.renamed`(带 `memorytalk.from` = 旧别名);`collapsed` 收起 / 展开整列,不记。返回新画布。列不存在 → 404。

## DELETE /api/works/{work_id}/columns/{column_id}

删一列,返回新画布,点 `column.removed`。删掉的编号不再发。

| 错误 | 状态 |
|---|---|
| 列不存在 | 404 `not_found` |
| 列里还有工作单元(只有空列能删) | 409 `conflict` |
| 这是最后一列 | 409 `conflict` |

---

## GET /api/works/{work_id}/worklets

```json
[{"id": "work_…-w1", "uri": "codex:///w", "scheme": "codex", "cwd": "/w",
  "created_at": "…", "last_attached": "…", "alive": true, "window": null, "handle": null}]
```

按开的先后(编号)排。`alive` 现算(问 server);活着的带 `window` / `handle`。现场自己没了、`worklet` 段还开着的,顺手把段结束成 `gone`(status Unset)。

## POST /api/works/{work_id}/worklets

在 work 里打开一个块:先验(work 没归档、列存在、URI 有协议;拿协议去 server 那里寻址,声明了的 server,否则 default)→ 取号(`works.next_worklet`)→ 建现场 → 登记工作单元并摆上画布(`works.db` 一个事务,`version + 1`)→ 开 `worklet` 段 → 交回窗 + 把手。建现场失败则什么都不写、不留登记(号不还);登记那一步失败(列刚好被删了、work 刚好被归档了 → 409),刚建的现场销毁掉。轨迹写失败只记日志,照样 201。

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
 "alive": true,
 "window": {"url": "http://127.0.0.1:43179/?arg=work_…-w1", "embed": "http://127.0.0.1:43179/?arg=work_…-w1"},
 "handle": {"kind": "tmux+transcript", "capabilities": ["send", "rounds"]}}
```

- 由哪个 server 建的不对外——`https://` 走 http server、`vim://` 走 default,调用方不感知。
- `window.url` 是 tmuxd 自带的 ttyd 地址(`http://<host>:<port>/?arg=<worklet_id>`);http 工作单元是 URL 本身。
- id `<work_id>-w<n>` 在 work 内单调递增、不复用:关掉 `-w1` 再开一个是 `-w2`(计数是 `works.next_worklet`)。
- 副作用:`worklets` 插一行(连同摆在哪);终端类起一个 tmux 会话(名 = 工作单元 id);进画布那一列末尾;开一个 `worklet` 段(带 uri / scheme / server 和放进的列)。

| 错误 | 状态 |
|---|---|
| work 已归档 | 409 `conflict` |
| `column` 不存在(先验,不建现场、不留登记) | 404 `not_found` |
| URI 没协议 | 400 `bad_uri` |
| 要跑的命令不在 PATH(如 `vim://` 走 default 但没装 vim) | 400 `cmd_not_found` |
| tmux 起不来 | 502 `platform` |

## POST /api/works/{work_id}/worklets/{worklet_id}/attach

重入:同一工作单元再次打开,幂等取回同一现场(tmux 会话还在就直接 attach,没了就按原 URI 重建)。返回同上,`last_attached` 更新。这个工作单元没有开着的 `worklet` 段(现场没了 / 归档后又重新打开)就开新的一段。

| 错误 | 状态 |
|---|---|
| work 已归档(冻住的工作单元不再起现场、不开段;正在归档时点的重入等归档做完,一样 409) | 409 `conflict` |
| 工作单元不存在 | 404 `not_found` |

## DELETE /api/works/{work_id}/worklets/{worklet_id}

关闭即回收:先最后收一次 round(agent 类,尽力而为;work 已归档就不收,归档时收过了)→ 销毁现场(tmuxd `session.kill()`)→ 删登记、从格子里拿掉(一个事务)→ 结束 `worklet` 段(`memorytalk.end.reason = detached`,带结束时所在的列和关它的人;开着的 `agent.turn` 跟着结束)。已经没有开着的段(现场没了 / 归档过、重新打开后没重入)就不动段,打一个 `worklet.closed` 点(带当时的列和关它的人)。**200**,`data: null`。

## POST /api/works/{work_id}/worklets/{worklet_id}/move

挪工作单元:左右挪 = 换列放末尾,上下挪 = 同列换 `index`,一个接口。

```json
{"column": "c1", "index": 0}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `column` | 是 | 挪到哪一列(`c<编号>`) |
| `index` | 否 | 列里从上数第几个(从 0 起,超出按末尾算;负数 → 422);不给 = 末尾 |

返回新画布。位置真变了才打点 `worklet.moved`(去哪:`memorytalk.column.*` + `memorytalk.index`;从哪:`memorytalk.from.column.*` + `memorytalk.from.index`)。工作单元不存在或不在画布上、目标列不存在 → 404。

## PATCH /api/works/{work_id}/worklets/{worklet_id}

`{"collapsed": true}` 收起 / 展开这个工作单元的格子。返回新画布,不进轨迹。工作单元不存在或不在画布上 → 404。

## GET /api/works/{work_id}/worklets/{worklet_id}/rounds

agent 工作单元的工作单元痕迹。work 运行中时先从把手同步:按 cwd + 工作单元创建时间定位平台记录文件,新 round 追加进 `worktrace.db` 的 `rounds` 表(按 `id` 去重),有新的就重切一遍 `agent.turn` 段;然后按追加的先后返回全部。

```json
[{"id": "u1", "timestamp": "2026-09-05T10:00:00Z", "role": "human", "text": "把配置改成环境变量"},
 {"id": "a1", "timestamp": "…", "role": "assistant", "text": "好\n[Edit] {\"f\": \"config.py\"}"}]
```

没有 `rounds` 能力的工作单元(bash / http)返回 `[]`(bash)或 `[]`(http)——不报错,因为「没有痕迹」是合法状态。
