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
  "memory": "/home/me/.memory.talk/memory",
  "works": "/home/me/.memory.talk/works",
  "workspace": "/home/me/workspace",
  "tmux_socket": "tmuxd-memorytalk",
  "tmuxd": {"port": 43179, "bind": "127.0.0.1", "url_host": null}
}
```

`tmux_socket` 是 tmuxd 实际用的 tmux socket(`tmuxd-<MEMORY_TALK_TMUX_SOCKET>`);`tmuxd` 是那扇窗在哪(ttyd 端口、绑哪、对外写什么 host)。
