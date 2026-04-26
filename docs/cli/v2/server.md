# server

管理本地 API 服务。v2 CLI 的所有命令都通过 HTTP 调该服务。

端口从 `settings.json` 的 `server.port` 读取（默认 7788），详见 [settings.md](../../structure/v2/settings.md)。

## server start

启动 API 服务（后台守护进程）。

```bash
memory-talk server start [--data-root PATH] [--json]
```

### Text（默认）

```
started · pid=12345 · port=7788
```

启动失败：

```
error: server failed to start (exit_code=2)
[memory-talk] embedding startup check failed: openai embedder: ...
```
（错误细节到 stderr，exit 1）

已在运行：

```
already_running · pid=12345 · port=7788
```

### JSON（`--json`）

```json
{"status": "started", "pid": 12345, "port": 7788}
```

```json
{"status": "failed", "exit_code": 2, "error": "..."}
```

```json
{"status": "already_running", "pid": 12345, "port": 7788}
```

## server stop

```bash
memory-talk server stop [--data-root PATH] [--json]
```

### Text

```
stopped · pid=12345
```

未运行：

```
not_running
```

### JSON

```json
{"status": "stopped", "pid": 12345}
```

```json
{"status": "not_running"}
```

## server status

直接调 API，能连上就是 running（同时返回数据统计），连不上就是 not_running。

```bash
memory-talk server status [--data-root PATH] [--json]
```

### Text（运行中）

```
status:    running
data_root: /home/user/.memory-talk
settings:  /home/user/.memory-talk/settings.json
sessions:  12
cards:     47
links:     23
searches:  108
embedding: dummy
vector:    lancedb
relation:  sqlite
```

### Text（未运行）

```
status:    not_running
data_root: /home/user/.memory-talk
settings:  /home/user/.memory-talk/settings.json
```

### JSON

```json
{
  "data_root": "/home/user/.memory-talk",
  "settings_path": "/home/user/.memory-talk/settings.json",
  "status": "running",
  "sessions_total": 12,
  "cards_total": 47,
  "links_total": 23,
  "searches_total": 108,
  "vector_provider": "lancedb",
  "relation_provider": "sqlite",
  "embedding_provider": "dummy"
}
```

`searches_total` 是 v2 新增字段——v2 把 search 作为主读路径，这个数字能快速看出"这台机器的记忆被多频繁地检索"。
