# System API

## GET /api/system/health

```json
{"ok": true}
```

永远 200。将来是 Docker `HEALTHCHECK` 与 `start` 等就绪的探针。

## GET /api/system/info

```json
{
  "home": "/home/me/.memory.talk",
  "metas": "/home/me/.memory.talk/metas",
  "store": {"family": "fs", "backend": "LocalFS"},
  "works_db": "/home/me/.memory.talk/works.db",
  "worktrace_db": "/home/me/.memory.talk/worktrace.db",
  "workspace": "/home/me/workspace",
  "tmux_socket": "tmuxd-memorytalk",
  "tmuxd": {"listen": "unix", "socket": "/home/me/.memory.talk/tmuxd/ttyd.sock", "mount": "/surface/tmuxd"}
}
```

`store` 是 users / auth 的存储(按 `MEMORY_TALK_STORE`);work 固定是两个 sqlite:`works_db`(现在)和 `worktrace_db`(经过),路径来自 `MEMORY_TALK_WORKS_DB` / `MEMORY_TALK_WORKTRACE_DB`(默认在 home 下),`memory.talk server status` 打出来。`tmux_socket` 是 tmuxd 实际用的 tmux socket(`tmuxd-<MEMORY_TALK_TMUX_SOCKET>`);`tmuxd` 是那扇窗在哪(ttyd 听的 unix socket、挂在哪个路径下)。
