# services/work_servers —— 现场怎么建

协议 → server 的那一层(设计:[work-server.md](../../../../docs/designs/v5/work-server.md))。具体的 server 在 [`backend/work_servers/`](../../work_servers/README.md),这里是它们共用的小件、注册表和 URI 解析。每个 server 文件自己写 `__init__`(拿注入的 tmuxd)和 `open`(调 `tmuxd.session`),像 controller 一样一眼能看到。

| 文件 | 重点 |
|---|---|
| `__init__.py` | `WorkServerService(runtime)`:起一份 `Tmuxd`(自己的 socket / ttyd / state,`close()` 时收掉 ttyd),装载所有 server;`resolve(uri)` 找谁响应;`open(worklet_id, uri, since_mtime)` 建(或取回)现场,交回 `(Live, handle)`;`handle` / `alive` / `destroy` 按 server 名转发;`list()` 给 `/api/works/servers` |
| `registry.py` | `Registry`:先查各 server 自己声明的 `protocols`,没人声明的协议去 `default`;`by_name` / `infos` |
| `uri.py` | `parse_uri(raw)` → `ParsedUri`:`scheme:///path?query`,终端类 path 是工作目录,http 类看 host |
| `terminal.py` | **不是基类,是小件**:`WorkServer` Protocol(契约面:`info` / `open` / `handle` / `alive` / `window` / `destroy`);`resolve_command(uri, workspace, cmd)` 算 cwd 和 argv(命令不在 PATH → `cmd_not_found`);`open_session(tmuxd, id, cwd, argv)` = `tmuxd.session(...)`,幂等,tmuxd 的错误变 `platform`;`session_window` / `kill_session`;`TmuxHandle(tmuxd, id)`:把手 = `alive` / `send`(按 id 懒取)。实现面是 **tmuxd**(pip 库,tmux + ttyd),只写不读,没有抓屏 |
| `agent.py` | `AgentHandle(TmuxHandle)`:agent 类的把手,多一项 `rounds()`——用 `adapters/` 里对应平台的 adapter 从会话记录文件读 round |
| [`adapters/`](adapters/README.md) | 各平台会话记录 → `Round` |
