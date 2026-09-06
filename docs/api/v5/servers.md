# Servers API

server 是认领协议、建现场、交回窗 + 把手的那层。本页只有观测端点——**建现场走 [`POST /api/tasks/{id}/members`](tasks.md#post-apitaskstask_idmembers)**,因为现场总是某个 task 的成员。字段见 [`../../structure/v5/server.md`](../../structure/v5/server.md)。

## GET /api/servers

```json
[
  {"name": "claude", "claims": ["claude"], "description": "Claude Code:tmux 现场 + 读 ~/.claude/projects 会话记录"},
  {"name": "codex",  "claims": ["codex"],  "description": "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"},
  {"name": "kimi",   "claims": ["kimi"],   "description": "Kimi Code:tmux 现场 + 读 ~/.kimi-code/sessions 会话记录"},
  {"name": "http",   "claims": ["http", "https"], "description": "外链直嵌;本地服务经网关代理;把手为空"},
  {"name": "bash",   "claims": ["bash", "*"], "description": "bash:// 以及任何 PATH 里的命令名 → tmux 会话(约定优于注册)"}
]
```

顺序就是解析顺序:显式名单在前,`"*"` 兜底在后。

## GET /api/servers/resolve

一个 URI 会请求到哪个 server,不建现场。

| 参数 | 说明 |
|---|---|
| `uri` | 必填 |

```json
{"uri": {"raw": "vim:///w/a.txt", "scheme": "vim", "path": "/w/a.txt", "host": "", "port": null, "query": {}},
 "server": "bash"}
```

| 错误 | 状态 |
|---|---|
| 没协议 | 400 `bad_uri` |
| 没 server 认领,PATH 也没这个命令 | 400 `no_server` |

> `resolve` 只看协议;`cmd_not_found`(server 认领了但命令不在 PATH)只在真正 open 时才会出现——目前只有 `bash` 一个兜底 server,而它认领的条件就是命令在 PATH,所以两者在实践里重合。
