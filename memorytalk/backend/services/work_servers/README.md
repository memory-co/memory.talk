# services/work_servers —— 现场怎么建

协议 → server 的那一层(设计:[work-server.md](../../../../docs/designs/v5/work-server.md))。具体的 server 在 [`backend/work_servers/`](../../work_servers/README.md),这里是它们共用的基类、注册表和 URI 解析。

| 文件 | 重点 |
|---|---|
| `__init__.py` | `WorkServerService(runtime)`:装载所有 server;`resolve(uri)` 找谁响应;`open(session_id, uri, since_mtime)` 建(或取回)现场,交回 `(Live, handle)`;`handle` / `alive` / `destroy` 按 server 名转发;`list()` 给 `/api/works/servers` |
| `registry.py` | `Registry`:先查各 server 自己声明的 `protocols`,没人声明的协议去 `default`;`by_name` / `infos` |
| `uri.py` | `parse_uri(raw)` → `ParsedUri`:`scheme:///path?query`,终端类 path 是工作目录,http 类看 host |
| `terminal.py` | `Tmux(socket)`:`has` / `new` / `kill` / `send` / `capture`(都是 `tmux -L <socket> …`);`TmuxHandle`:把手 = `alive` / `capture` / `send`;`TerminalBase`:终端类 server 的基类——`command(uri)` 决定跑什么,`resolve(uri)` 算 cwd 和命令,`open()` 幂等建 tmux 会话并交回窗(配了 ttyd 才有)+ 把手,`alive` / `destroy` |
| `agent.py` | `AgentBase(TerminalBase)`:agent 类 server,把手多一项 `rounds()`——用 `adapters/` 里对应平台的 adapter 从会话记录文件读 round;`AgentHandle` |
| [`adapters/`](adapters/README.md) | 各平台会话记录 → `Round` |
