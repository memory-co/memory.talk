# Works API

work 树、画布、工作单元(现场)、user、痕迹、事件、召回。登录后的请求(身份来自 token,见 [auth.md](auth.md)),凡会动某个 work 的(建、改、画布上的每个动作、开 / 重入 / 关工作单元、打开 work 本身),都会把这个人记进该 work 的users 名单;记事件的动作还把这个人写进事件的 `by`。字段语义见 [`../../structure/v5/work.md`](../../structure/v5/work.md)。

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
   "status": "running", "created_at": "…", "archived_at": null,
   "children": [
     {"id": "work_…a1b2", "goal": "实现 issue", "parent": "work_…2f2f", "status": "archived",
      "created_at": "…", "archived_at": "…", "children": []}
   ]}
]
```

`children` 读时从各 `work.json` 的 `parent` 拼出来。父不存在的节点当作根。

## POST /api/works

开工。

```json
{"goal": "实现 work", "parent": "work_…2f2f"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `goal` | 是 | 一句话 |
| `parent` | 否 | 挂到哪个 work 下;不存在 → 404 |

**201** 返回 Work(`status: "running"`,`created_by` = 请求头里的 user,没带则 `null`)。副作用:`works/<id>/work.json` + 一条 `created` 事件。

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

返回 Work。404 `not_found`。

## PATCH /api/works/{work_id}

```json
{"goal": "…", "status": "archived"}
```

两个字段都可选。`status` 只收 `running` / `archived`,别的值 → 422。规则:

| 目标 | 规则 | 副作用 |
|---|---|---|
| `running` | 无(可从 `archived` 改回) | `archived_at` 清空 |
| `archived` | 无——**不看子 work**,父子各自归档 | `archived_at`(已归档则保留);**冻结**:工作单元现场全部销毁(登记留着),事件 `status` + `frozen` |

归档后:`POST …/worklets` → 409;`rounds` 不再从把手同步。

## GET /api/works/{work_id}/events

```json
[
  {"ts": "…", "type": "created", "data": {"goal": "…", "parent": null, "by": "alice"}},
  {"ts": "…", "type": "column.added", "data": {"by": "alice", "column": {"id": "c2", "alias": ""}}},
  {"ts": "…", "type": "column.renamed", "data": {"by": "alice", "column": {"id": "c2", "alias": "测试"}, "from": ""}},
  {"ts": "…", "type": "worklet.attached", "data": {"by": "alice", "worklet": "…-w1", "uri": "codex:///w", "server": "codex", "column": {"id": "c2", "alias": "测试"}}},
  {"ts": "…", "type": "worklet.moved", "data": {"by": "bob", "worklet": "…-w1", "from": {"column": {"id": "c2", "alias": "测试"}, "index": 0}, "to": {"column": {"id": "c1", "alias": ""}, "index": 1}}},
  {"ts": "…", "type": "worklet.detached", "data": {"by": "bob", "worklet": "…-w1", "uri": "codex:///w", "column": {"id": "c1", "alias": ""}}},
  {"ts": "…", "type": "status", "data": {"by": "alice", "from": "running", "to": "archived"}},
  {"ts": "…", "type": "frozen", "data": {"by": "alice"}}
]
```

每条都带 `by`(登录态里的人,没有则 `null`)。画布动作带列标记 `{"id": "c<n>", "alias": "<当时的别名>"}`:`id` 是身份,`alias` 是事件发生那一刻的快照,后来改名不回改。收起 / 展开(列或工作单元)不记事件。各 `type` 的 `data` 见 [structure work.md#event](../../structure/v5/work.md#event)。旧事件没有 `by` / `column` 的照原样返回,不回填。

---|---|
| `dir` | 只给这个目录之下的对象;空 = 全部 |
| `layer` | 哪一层的目录,默认 `card` |

## GET /api/works/{work_id}/inbox

收件箱:被 `manager.json` 路由过来的变动——Metas 里这个 work 管的那一片的每次提交,以及子 work(或 `manager.json` 指过来的 work)的创建 / 状态变化。append-only。

```json
[{"ts": "…", "layer": "issue", "path": "memory.talk/配置/该走文件还是环境变量", "subject": "position …#p2: 只用环境变量",
  "sha": "…", "by": "alice", "routed_by": "memory.talk"},
 {"ts": "…", "layer": "work", "path": "work_…child", "subject": "status running -> archived", "sha": null, "by": null, "routed_by": "parent"}]
```

## GET /api/works/{work_id}/manager

这个 work 的变动打给谁:`works/<id>/manager.json` 里的 work,没有则父 work,根 → `null`。

## PUT /api/works/{work_id}/manager

`{"work": "work_…"}` 改写默认;`{"work": null}` 删掉、回到父。返回 `{"work": …}`。

```
memory.talk/
  - 配置只来自环境变量  (memory.talk/配置只来自环境变量)
  - Python 3.12  (memory.talk/Python-3.12)
```

---

## GET /api/works/{work_id}/users

user:谁当前正在操作、谁历史操作过。只做可见性,不做权限。

```json
{"current": [{"user": "alice", "first_seen": "…", "last_seen": "…", "ops": 7, "active": true}],
 "history": [{"user": "alice", "first_seen": "…", "last_seen": "…", "ops": 7, "active": true},
             {"user": "bob",   "first_seen": "…", "last_seen": "…", "ops": 2, "active": false}]}
```

`active` = 最近 120 秒内动过;`current` 是 `history` 里 active 的那些;`history` 按最近活动倒序。

## POST /api/works/{work_id}/users/touch

心跳:「我在操作这个 work」。身份来自登录态。返回同上。前端开着 work 页面时每 30 秒调一次。

---

## GET /api/works/{work_id}/canvas

```json
{"version": 3, "next_column": 4,
 "columns": [{"id": "c1", "alias": "调研", "panels": [{"worklet": "work_…-w1", "collapsed": false}, {"worklet": "work_…-w2", "collapsed": true}], "collapsed": false},
             {"id": "c3", "alias": "", "panels": [{"worklet": "work_…-w4", "collapsed": false}], "collapsed": true}]}
```

布局 = 几列,每列从上到下摆工作单元;工作单元可收起(只剩标题行),整列也可收起(缩成一条窄边)。**一列 = 固定编号 + 别名**:`id` 是 `c<编号>`,服务端发、单调递增、永不改不复用(删过列编号就不连续,如上例没有 `c2`);`alias` 是别名,可空可重名,改名只改它(空 = 前端显示「列 <编号>」,否则「列 <编号> · <别名>」)。**至少一列**:新 work 的画布就是 `{"version": 0, "next_column": 2, "columns": [{"id": "c1", …}]}`。旧数据读时规整:`name` 当 `alias` 读,不是 `c<n>` 形式的列 id 按从左到右接着发新号,`next_column` 取最大编号 + 1。

**画布没有整份写口**(`PUT …/canvas` 已撤,→ 405):每个动作一个请求,服务端在当前画布上做、存回、`version + 1`、记事件,返回新画布。不需要客户端带 `version`(服务端串行,两人各做各的动作都成功);`version` 只用来判断本地缓存旧没旧。**画布是视图**——它不建、不删工作单元;但跟着工作单元走:`POST …/worklets` 开出来的工作单元进指定列末尾,`DELETE` 掉的自动从格子里拿掉,这两处也 `version + 1`。

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

**201** 返回新画布;新列 id = `c<next_column>`,`next_column + 1`。事件 `column.added`。`beside` 不存在 → 404。

## PATCH /api/works/{work_id}/columns/{column_id}

```json
{"alias": "测试", "collapsed": true}
```

两个字段都可选。`alias` 改别名(编号不动;首尾空白去掉;空串 = 清掉别名),变了才记事件 `column.renamed`(带 `from` = 旧别名);`collapsed` 收起 / 展开整列,不记事件。返回新画布。列不存在 → 404。

## DELETE /api/works/{work_id}/columns/{column_id}

删一列,返回新画布,事件 `column.removed`。删掉的编号不再发。

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

`alive` 现算(问 server);列表不带 `window` / `handle`(attach 时才给)。

## POST /api/works/{work_id}/worklets

在 work 里打开一个块:拿协议去 server 那里寻址(声明了的 server,否则 default)→ 幂等建现场 → 登记工作单元 → 交回窗 + 把手。建现场失败则不留登记。

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
- id `<work_id>-w<n>` 在 work 内单调递增、不复用:关掉 `-w1` 再开一个是 `-w2`(计数存在 `seq`)。
- 副作用:`worklets.json` 追加一条;终端类起一个 tmux 会话(名 = 工作单元 id);进画布那一列末尾;事件 `worklet.attached`(带 `column`)。

| 错误 | 状态 |
|---|---|
| work 已归档 | 409 `conflict` |
| `column` 不存在(先验,不建现场、不留登记) | 404 `not_found` |
| URI 没协议 | 400 `bad_uri` |
| 要跑的命令不在 PATH(如 `vim://` 走 default 但没装 vim) | 400 `cmd_not_found` |
| tmux 起不来 | 502 `platform` |

## POST /api/works/{work_id}/worklets/{worklet_id}/attach

重入:同一工作单元再次打开,幂等取回同一现场(tmux 会话还在就直接 attach,没了就按原 URI 重建)。返回同上,`last_attached` 更新。

## DELETE /api/works/{work_id}/worklets/{worklet_id}

关闭即回收:销毁现场(tmuxd `session.kill()`)+ 删登记 + 从格子里拿掉 + 事件 `worklet.detached`(带 `uri` 和原来所在的 `column`;不在画布上则 `column: null`)。**200**,`data: null`。

## POST /api/works/{work_id}/worklets/{worklet_id}/move

挪工作单元:左右挪 = 换列放末尾,上下挪 = 同列换 `index`,一个接口。

```json
{"column": "c1", "index": 0}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `column` | 是 | 挪到哪一列(`c<编号>`) |
| `index` | 否 | 列里从上数第几个(从 0 起,超出按末尾算;负数 → 422);不给 = 末尾 |

返回新画布。位置真变了才记事件 `worklet.moved`(`from` / `to` 各是 `{column, index}`)。工作单元不存在或不在画布上、目标列不存在 → 404。

## PATCH /api/works/{work_id}/worklets/{worklet_id}

`{"collapsed": true}` 收起 / 展开这个工作单元的格子。返回新画布,不记事件。工作单元不存在或不在画布上 → 404。

## GET /api/works/{work_id}/worklets/{worklet_id}/rounds

agent 工作单元的工作单元痕迹。work 运行中时先从把手同步:按 cwd + 工作单元创建时间定位平台记录文件,新 round 追加进 `rounds.jsonl`(按 `id` 去重);然后返回全部。

```json
[{"id": "u1", "timestamp": "2026-09-05T10:00:00Z", "role": "human", "text": "把配置改成环境变量"},
 {"id": "a1", "timestamp": "…", "role": "assistant", "text": "好\n[Edit] {\"f\": \"config.py\"}"}]
```

没有 `rounds` 能力的工作单元(bash / http)返回 `[]`(bash)或 `[]`(http)——不报错,因为「没有痕迹」是合法状态。
