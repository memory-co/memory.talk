# Servers API

server 是建现场、交回窗 + 把手的那层;**server 名 = 协议名**(URI 里 `://` 前面那个)。本页只有观测端点——**建现场走 [`POST /api/tasks/{id}/members`](tasks.md#post-apitaskstask_idmembers)**,因为现场总是某个 task 的成员。字段见 [`../../structure/v5/server.md`](../../structure/v5/server.md)。

## GET /api/servers

```json
[
  {"name": "bash",   "description": "bash:///<cwd> → tmux 会话里的 bash"},
  {"name": "claude", "description": "Claude Code:tmux 现场 + 读 ~/.claude/projects 会话记录"},
  {"name": "codex",  "description": "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"},
  {"name": "http",   "description": "网页块:外链直嵌,本地服务经网关代理;把手为空"},
  {"name": "https",  "description": "网页块:外链直嵌,本地服务经网关代理;把手为空"},
  {"name": "kimi",   "description": "Kimi Code:tmux 现场 + 读 ~/.kimi-code/sessions 会话记录"}
]
```

一项 = `backend/servers/` 下一个文件。`name` 就是它服务的协议。

## GET /api/servers/resolve

一个 URI 会请求到哪个 server,不建现场。答案永远是协议名本身——这个端点的价值是顺便把 URI 解析结果给你,以及在协议没有 server 时提前报错。

| 参数 | 说明 |
|---|---|
| `uri` | 必填 |

```json
{"uri": {"raw": "codex:///w/memory.talk", "scheme": "codex", "path": "/w/memory.talk", "host": "", "port": null, "query": {}},
 "server": "codex"}
```

| 错误 | 状态 |
|---|---|
| 没协议 | 400 `bad_uri` |
| 没有这个协议的 server(如 `vim://` 而没有 `servers/vim.py`) | 400 `no_server` |

> `cmd_not_found`(server 在、但同名命令不在 PATH)只在真正 open 时出现,`resolve` 不探 PATH。
