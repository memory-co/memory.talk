# Servers API

server 是建现场、交回窗 + 把手的那层。**每个 server 自己声明响应哪些协议**,一个可以多个;没人声明的协议去 **default**(背后是 bash 把协议名当命令跑,调用方不感知)。本页只有观测端点——**建现场走 [`POST /api/tasks/{id}/sessions`](tasks.md#post-apitaskstask_idmembers)**,因为现场总是某个 task 的会话。字段见 [`../../structure/v5/server.md`](../../structure/v5/server.md)。

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

没有「先问一下这个 URI 归谁」的端点。**寻址在打开会话那一刻自动发生**(`POST /api/tasks/{id}/sessions`):协议在哪个 server 的 `protocols` 里就去哪个,没有就 default;调用方拿到的是窗和把手,不需要、也看不到是谁建的。
