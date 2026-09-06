# Servers API

server 是建现场、交回窗 + 把手的那层。**每个 server 自己声明响应哪些协议**,一个可以多个;没人声明的协议去 **default**(背后是 bash 把协议名当命令跑,调用方不感知)。本页只有观测端点——**建现场走 [`POST /api/tasks/{id}/members`](tasks.md#post-apitaskstask_idmembers)**,因为现场总是某个 task 的成员。字段见 [`../../structure/v5/server.md`](../../structure/v5/server.md)。

## GET /api/servers

```json
[
  {"name": "bash",    "protocols": ["bash"],          "description": "bash:///<cwd> → tmux 会话里的 bash"},
  {"name": "claude",  "protocols": ["claude"],        "description": "Claude Code:tmux 现场 + 读 ~/.claude/projects 会话记录"},
  {"name": "codex",   "protocols": ["codex"],         "description": "Codex:tmux 现场 + 读 ~/.codex/sessions 会话记录"},
  {"name": "http",    "protocols": ["http", "https"], "description": "网页块:外链直嵌,本地服务经网关代理;把手为空"},
  {"name": "kimi",    "protocols": ["kimi"],          "description": "Kimi Code:tmux 现场 + 读 ~/.kimi-code/sessions 会话记录"},
  {"name": "default", "protocols": [],                "description": "兜底:没有专门 server 的协议,把协议名当命令名在 tmux 里跑"}
]
```

一项 = `backend/servers/` 下一个文件。`protocols` 是它自己声明的;`default` 不声明、永远排最后。

## GET /api/servers/resolve

一个 URI 会请求到哪个 server,不建现场。

| 参数 | 说明 |
|---|---|
| `uri` | 必填 |

```json
{"uri": {"raw": "https://x.y/z", "scheme": "https", "path": "/z", "host": "x.y", "port": null, "query": {}},
 "server": "http"}
```

```json
{"uri": {"raw": "vim:///w/a.txt", "scheme": "vim", "path": "/w/a.txt", "host": "", "port": null, "query": {}},
 "server": "default"}
```

| 错误 | 状态 |
|---|---|
| 没协议 | 400 `bad_uri` |
| 连 default 都没有 | 400 `no_server` |

> `resolve` 不探 PATH:`vim://` 一律答 `default`;`vim` 装没装,要到真正 open(`POST /api/tasks/{id}/members`)时才知道——没装报 `400 cmd_not_found`。
