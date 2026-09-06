# Task + Canvas + Session + Member + Round + Event

做事层的六个对象,全部住在 `tasks/<task_id>/` 目录下,裸文件。机制见 [`../../works/v5/task.md`](../../works/v5/task.md)。

## Task

树上一个节点。

```json
{
  "id": "task_202609052302072f2f",
  "goal": "把 v5 做出来",
  "project": "/home/me/memory.talk",
  "parent": null,
  "status": "doing",
  "created_at": "2026-09-05T23:02:07Z",
  "done_at": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `task_<时间戳><4hex>`,自动 |
| `goal` | string | 它是什么事(一句话) |
| `project` | string | 在哪个项目(工作目录);可空 |
| `parent` | string \| null | 属于哪件更大的事;`null` = 根。**task 之间只有这一种直接关系** |
| `status` | `todo` \| `doing` \| `done` \| `abandoned` | 三层里只有 task 有状态 |
| `created_at` | ISO 8601 | |
| `done_at` | ISO 8601 \| null | `done` / `abandoned` 时写;回到 `todo` / `doing` 清空 |

**状态规则**:
- `done` 要求所有子 task 都是 `done` 或 `abandoned`,否则 `409`(完成从叶子往上收拢)。
- 进入 `done` / `abandoned` 即**冻结**:所有会话的现场销毁、登记留着、不能再 attach;`rounds` 不再从把手同步,只读已记的。
- 没有 `doing` 的自动推断——开工 / 在做 / 待做由人或 agent 标。

**读视图 `TaskNode`** = Task + `children: TaskNode[]`(读时拼出来,不存)。

## Canvas

task 的画布:24×16 网格上的矩形剖分。**只是视图**——重排不改变 task 的会话和目的。

```json
{
  "cols": 24, "rows": 16, "version": 3,
  "panels": [
    {"id": "p1", "uri": "file:///home/me/memory.talk", "session": null, "x": 0, "y": 0, "w": 6, "h": 16},
    {"id": "p2", "uri": "codex:///home/me/memory.talk", "session": "task_2026…2f2f-s1", "x": 6, "y": 0, "w": 18, "h": 16}
  ]
}
```

| 字段 | 说明 |
|---|---|
| `version` | 乐观锁;`PUT` 必须带当前值,成功后 +1 |
| `panels[].id` | 前端自定,画布内唯一 |
| `panels[].uri` | 这个块装什么(构造形态 URI,不含身份参数) |
| `panels[].session` | 装的是哪个会话;终端类块必有,浏览器 / 文件类可无 |
| `x y w h` | 网格坐标;`x+w ≤ cols`、`y+h ≤ rows`、`w,h ≥ 1`,越界 `409` |

**跟 shellbase 唯一有意不同的地方**:块的身份不在 `(window, block)` 位置参数里,而在 `session`——把块拖到别的格子,会话不变。

## Session

task 的一个会话 = 一个现场。**在 task 里打开就是它的**,归属原生,不靠 cwd 推断。

```json
{
  "id": "task_202609052302072f2f-s1",
  "uri": "codex:///home/me/memory.talk",
  "scheme": "codex",
  "server": "codex",
  "cwd": "/home/me/memory.talk",
  "created_at": "2026-09-05T23:02:10Z",
  "last_attached": "2026-09-05T23:40:01Z"
}
```

| 字段 | 说明 |
|---|---|
| `id` | `<task_id>-s<n>`,task 内顺序编号;**就是 tmux 会话名**(终端类) |
| `uri` | 打开它用的 URI(原样) |
| `scheme` | URI 的协议 |
| `server` | 建它的 server 名;可以 ≠ `scheme`(`https` → `http`,`vim` → `default`) |
| `cwd` | server 解析出的工作目录(终端类);浏览器类为 `null` |
| `created_at` | 会话诞生时刻;agent 类 server 用它找「之后新出现的那份会话记录」 |
| `last_attached` | 最近一次重入 |

**读视图 `SessionView`** = Session + `alive`(问 server 现算)+ `window` / `handle`(attach / reattach 时返回,list 时不带)。

一个会话只属于一个 task、一个确定节点。要在别的事里用它的结论,走 issue / card,不搬会话。

## Member

**人**,不是现场。谁在操作 / 操作过这个 task;只做可见性,**不做权限**(整个实例给一个团队用)。机制见 [`../../works/v5/member.md`](../../works/v5/member.md)。

```json
{"user": "alice", "first_seen": "2026-09-06T08:00:00Z", "last_seen": "2026-09-06T09:12:40Z", "ops": 7}
```

| 字段 | 说明 |
|---|---|
| `user` | 团队里的一个人;客户端在请求头 `X-Memory-Talk-User` 里自报,服务端不校验 |
| `first_seen` / `last_seen` | 第一次 / 最近一次操作这个 task |
| `ops` | 操作次数(带身份的、会动这个 task 的请求 + 打开 + 心跳) |

**读视图 `Members`**:`{"current": [MemberView], "history": [MemberView]}`,`MemberView` = Member + `active`(最近 120 秒内动过,现算)。`current` 是 `history` 里 `active` 的子集;`history` 按最近活动倒序。

不带身份的请求照样能操作,只是不记名。

## Round

agent 会话的会话痕迹:从各平台的记录文件读出来、append-only 追加进 `rounds.jsonl`。

```json
{"id": "8b1e…", "timestamp": "2026-09-05T23:05:12Z", "role": "human", "text": "把配置改成环境变量"}
```

| 字段 | 说明 |
|---|---|
| `id` | 平台自己的消息 id(Claude Code 的 `uuid`、Kimi 的事件 `uuid`;Codex 用 `<文件名>:<行号>`);同步时按它去重 |
| `timestamp` | 平台原样透传(可能为空、格式异构;**不要拿它排序**,文件顺序就是时间顺序) |
| `role` | `human` / `assistant` / `tool` / `system` |
| `text` | 扁平化文本:工具调用写成 `[Name] args`,结果写成 `[result] …`,思考写成 `[thinking] …` |

只记这四项——round 是 issue 的原料(逐 round 标注、`#问题`),不是检索单元。

## Event

task 自己的时间线,append-only。v3 `events.jsonl` 在 v5 唯一保留的地方。

```json
{"ts": "2026-09-05T23:02:07Z", "type": "created", "data": {"goal": "把 v5 做出来", "parent": null}}
{"ts": "2026-09-05T23:02:10Z", "type": "session.attached", "data": {"session": "…-s1", "uri": "codex:///…", "server": "codex"}}
{"ts": "2026-09-06T01:00:00Z", "type": "status", "data": {"from": "doing", "to": "done"}}
{"ts": "2026-09-06T01:00:00Z", "type": "frozen", "data": {}}
```

| `type` | `data` |
|---|---|
| `created` | `goal`, `parent` |
| `status` | `from`, `to` |
| `frozen` | — (结束时现场已销毁) |
| `session.attached` | `session`, `uri`, `server` |
| `session.detached` | `session` |

## 存储

```
tasks/<task_id>/
├── task.json         原子写(临时文件 + rename)
├── canvas.json       原子写;不存在 = 空画布 version 0
├── sessions.json     原子写;数组(现场)
├── members.json      原子写;数组(人)
├── events.jsonl      只追加
└── sessions/<session_id>/rounds.jsonl   只追加
```

读写纪律照 shellbase:单写者(服务进程)、无缓存直读、任何时刻磁盘上都是完整 JSON。**不进 git**——task 记的是过程,git 记的是决定(见 [`../../works/v5/store.md`](../../works/v5/store.md) §4)。
