# work_servers —— 每个协议一个 server

每个文件一个 server,**server 自己声明它响应哪些协议**(`protocols`),一个 server 可以响应多个(http 响应 http + https)。基类在 [`services/work_servers/`](../services/work_servers/README.md)。

| 文件 | 协议 | 现场 | 把手 |
|---|---|---|---|
| `bash.py` | `bash://` | 到某目录起一个 bash(tmux 会话) | 终端把手 |
| `claude.py` | `claude://` | 终端里跑 Claude Code | 终端 + 读 `~/.claude/projects` 的 round |
| `codex.py` | `codex://` | 终端里跑 Codex CLI | 终端 + 读 `~/.codex/sessions` 的 round |
| `kimi.py` | `kimi://` | 终端里跑 Kimi Code CLI | 终端 + 读 `~/.kimi-code/sessions` 的 round |
| `http.py` | `http://` `https://` | 浏览器块:窗 = URL 本身 | `NoHandle`(把手为空,不撒谎) |
| `default.py` | 其余任何协议 | 协议名当命令名(`vim://`、`htop://`)到某目录在 tmux 里跑 | 终端把手 |

`__init__.py`:`Context(rt, tmuxd, workspace)` 是每个 server 拿到的运行环境(tmuxd 一个进程一份);`load(rt, tmuxd)` 用 `pkgutil` 扫这个目录,对每个模块调 `make(ctx)`,default 排最后(先查显式声明再兜底)。加一个 server = 加一个文件、写一个 `make(ctx)`。
