# Tasks API

task 树、画布、会话(现场)、成员(人)、痕迹、事件、召回。带 `X-Memory-Talk-User` 头的请求,凡会动某个 task 的(建、改、重排画布、开 / 重入 / 关会话、打开 task 本身),都会把这个人记进该 task 的成员名单。字段语义见 [`../../structure/v5/task.md`](../../structure/v5/task.md)。

---

## GET /api/tasks

task 树(森林)。

| 参数 | 说明 |
|---|---|
| `root` | 可选;只返回这个 task 为根的一棵(不存在 → 404) |

```json
[
  {"id": "task_…2f2f", "goal": "把 v5 做出来", "parent": null,
   "status": "doing", "created_at": "…", "done_at": null,
   "children": [
     {"id": "task_…a1b2", "goal": "实现 issue", "parent": "task_…2f2f", "status": "done",
      "created_at": "…", "done_at": "…", "children": []}
   ]}
]
```

`children` 读时从各 `task.json` 的 `parent` 拼出来。父不存在的节点当作根。

## POST /api/tasks

开工。

```json
{"goal": "实现 task", "parent": "task_…2f2f"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `goal` | 是 | 一句话 |
| `parent` | 否 | 挂到哪个 task 下;不存在 → 404 |

**201** 返回 Task(`status: "todo"`)。副作用:`tasks/<id>/task.json` + 一条 `created` 事件。

## GET /api/tasks/{task_id}

返回 Task。404 `not_found`。

## PATCH /api/tasks/{task_id}

```json
{"goal": "…", "status": "done"}
```

两个字段都可选。`status` 规则:

| 目标 | 规则 | 副作用 |
|---|---|---|
| `todo` / `doing` | 无 | `done_at` 清空 |
| `done` | 所有子 task 须为 `done` / `abandoned`,否则 **409** `conflict`(message 列出未完的子 task) | `done_at`;**冻结**:会话现场全部销毁(登记留着),事件 `status` + `frozen` |
| `abandoned` | 无 | 同上 |

结束后:`POST …/sessions` → 409;`rounds` 不再从把手同步。

## GET /api/tasks/{task_id}/events

```json
[
  {"ts": "…", "type": "created", "data": {"goal": "…", "parent": null}},
  {"ts": "…", "type": "session.attached", "data": {"session": "…-s1", "uri": "codex:///w", "server": "codex"}},
  {"ts": "…", "type": "status", "data": {"from": "doing", "to": "done"}},
  {"ts": "…", "type": "frozen", "data": {}}
]
```

## GET /api/tasks/{task_id}/recall

card → task 的接口:开工时注入的目录文本。`text/plain`。

| 参数 | 说明 |
|---|---|
| `dir` | 只给这个目录之下的卡;空 = 全部 |

```
memory.talk/
  - 配置只来自环境变量  (memory.talk/配置只来自环境变量)
  - Python 3.12  (memory.talk/Python-3.12)
```

不含 `deprecated` 的卡。

---

## GET /api/tasks/{task_id}/members

成员(**人**):谁当前正在操作、谁历史操作过。只做可见性,不做权限。

```json
{"current": [{"user": "alice", "first_seen": "…", "last_seen": "…", "ops": 7, "active": true}],
 "history": [{"user": "alice", "first_seen": "…", "last_seen": "…", "ops": 7, "active": true},
             {"user": "bob",   "first_seen": "…", "last_seen": "…", "ops": 2, "active": false}]}
```

`active` = 最近 120 秒内动过;`current` 是 `history` 里 active 的那些;`history` 按最近活动倒序。

## POST /api/tasks/{task_id}/members/touch

心跳:「我在操作这个 task」。身份来自 `X-Memory-Talk-User`;不带头则什么都不记。返回同上。前端开着 task 页面时每 30 秒调一次。

---

## GET /api/tasks/{task_id}/canvas

```json
{"cols": 24, "rows": 16, "version": 0, "panels": []}
```

从未写过 = `version 0`、空 `panels`。

## PUT /api/tasks/{task_id}/canvas

全量覆盖。

```json
{"version": 0,
 "panels": [{"id": "p1", "uri": "file:///w", "session": null, "x": 0, "y": 0, "w": 6, "h": 16},
            {"id": "p2", "uri": "codex:///w", "session": "task_…-s1", "x": 6, "y": 0, "w": 18, "h": 16}]}
```

| 错误 | 状态 |
|---|---|
| `version` ≠ 当前 | 409 `conflict` `canvas version 0 != 1` |
| 某块越界(`x+w > 24`、`y+h > 16`、`w/h < 1`、负坐标) | 409 `conflict` `panel p1 越界` |

成功返回新画布,`version + 1`。**画布是视图**——它不建、不删会话;会话走下面的端点。

---

## GET /api/tasks/{task_id}/sessions

```json
[{"id": "task_…-s1", "uri": "codex:///w", "scheme": "codex", "cwd": "/w",
  "created_at": "…", "last_attached": "…", "alive": true, "window": null, "handle": null}]
```

`alive` 现算(问 server);列表不带 `window` / `handle`(attach 时才给)。

## POST /api/tasks/{task_id}/sessions

在 task 里打开一个块:拿协议去 server 那里寻址(声明了的 server,否则 default)→ 幂等建现场 → 登记会话 → 交回窗 + 把手。建现场失败则不留登记。

```json
{"uri": "codex:///w/memory.talk"}
```

**201**:

```json
{"id": "task_…-s1", "uri": "codex:///w/memory.talk", "scheme": "codex",
 "cwd": "/w/memory.talk", "created_at": "…", "last_attached": "…",
 "alive": true,
 "window": {"url": null, "embed": null},
 "handle": {"kind": "tmux+transcript", "capabilities": ["capture", "send", "rounds"]}}
```

- 由哪个 server 建的不对外——`https://` 走 http server、`vim://` 走 default,调用方不感知。
- `window.url` 为 `null` = 没配 ttyd,只有把手没有画面。
- 副作用:`sessions.json` 追加一条;终端类起一个 tmux 会话(名 = 会话 id);事件 `session.attached`。

| 错误 | 状态 |
|---|---|
| task 已结束 | 409 `conflict` |
| URI 没协议 | 400 `bad_uri` |
| 要跑的命令不在 PATH(如 `vim://` 走 default 但没装 vim) | 400 `cmd_not_found` |
| tmux 起不来 | 502 `platform` |

## POST /api/tasks/{task_id}/sessions/{session_id}/attach

重入:同一会话再次打开,幂等取回同一现场(tmux 会话还在就直接 attach,没了就按原 URI 重建)。返回同上,`last_attached` 更新。

## DELETE /api/tasks/{task_id}/sessions/{session_id}

关闭即回收:销毁现场(`tmux kill-session`)+ 删登记 + 事件 `session.detached`。**204**。

## GET /api/tasks/{task_id}/sessions/{session_id}/capture

把手 `capture`:抓终端屏幕,`text/plain`。

| 参数 | 说明 |
|---|---|
| `lines` | 回看多少行,默认 200,`[1, 5000]` |

把手没有 `capture`(http 会话)→ 409 `conflict`。

## GET /api/tasks/{task_id}/sessions/{session_id}/rounds

agent 会话的会话痕迹。task 未结束时先从把手同步:按 cwd + 会话创建时间定位平台记录文件,新 round 追加进 `rounds.jsonl`(按 `id` 去重);然后返回全部。

```json
[{"id": "u1", "timestamp": "2026-09-05T10:00:00Z", "role": "human", "text": "把配置改成环境变量"},
 {"id": "a1", "timestamp": "…", "role": "assistant", "text": "好\n[Edit] {\"f\": \"config.py\"}"}]
```

没有 `rounds` 能力的会话(bash / http)返回 `[]`(bash)或 `[]`(http)——不报错,因为「没有痕迹」是合法状态。
