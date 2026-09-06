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
  "tasks": "/home/me/.memory.talk/tasks",
  "workspace": "/home/me/workspace",
  "tmux_socket": "memorytalk",
  "ttyd_url": null
}
```

`ttyd_url` 为 `null` 时,终端类成员的 `window.url` 也是 `null`——只有把手没有画面。
