# server

管理本地 API 服务。CLI 的所有数据命令通过 HTTP 调用此服务。

## server start

启动 API 服务（后台守护进程）。

```bash
memory-talk server start [--port 7788] [--data-root PATH]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--port` | `7788` | 监听端口 |
| `--data-root` | `~/.memory-talk` | 数据根目录 |

输出：
```json
{"status": "started", "pid": 12345, "port": 7788}
```

启动失败时（如端口占用、依赖缺失）：
```json
{"status": "failed", "exit_code": 1, "error": "...错误信息..."}
```

已在运行时：
```json
{"status": "already_running", "pid": 12345, "port": 7788}
```

## server stop

停止 API 服务。

```bash
memory-talk server stop [--data-root PATH]
```

输出：
```json
{"status": "stopped", "pid": 12345}
```

## server status

检查 API 服务是否在运行。

```bash
memory-talk server status [--data-root PATH]
```

运行中：
```json
{"status": "running", "pid": 12345}
```

进程崩溃（有错误日志）：
```json
{"status": "crashed", "error": "...最近的错误信息..."}
```

未运行：
```json
{"status": "not_running"}
```
