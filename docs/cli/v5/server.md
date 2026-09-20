# server

本地 API 服务的生命周期:后台守护,照 shellbase 的 `start / stop / status / daemon`。

```
memory.talk server start   [--host 127.0.0.1] [--port 8000] [--home ~/.memory.talk]
memory.talk server stop
memory.talk server restart
memory.talk server status  [--json]
memory.talk server daemon  [--host] [--port]      # 前台阻塞,日志走 stdout —— 容器 / systemd 用
```

## start

后台拉起 API(uvicorn),等它就绪,把地址、日志路径打出来;关掉终端不会被带走(`start_new_session`)。已经在跑 → 直接打印现状,退出码 0。

```
memory.talk 已启动(pid 12345)
  地址    http://127.0.0.1:8000
  文档    http://127.0.0.1:8000/docs
  存储    fs  ~/.memory.talk
  日志    ~/.memory.talk/server.log
  停止    memory.talk server stop
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 只绑本机;`0.0.0.0` = 对外(没有鉴权,别在公网这么干) |
| `--port` | `8000` | |
| `--home` | `MEMORY_TALK_HOME` / `~/.memory.talk` | 根;`server.pid` / `server.log` / `instance.json` 都在这 |

起不来(端口被占、依赖缺)→ 把日志尾巴打出来,退出码 1。

## stop

按 `server.pid` 发 SIGTERM,等 5 秒不退再 SIGKILL。没在跑 → 提示,退出码 0。**不动 tmux 会话**——现场活得比服务久,下次 `start` 后按登记重入。

## restart

`stop` + `start`,参数沿用 `instance.json` 里记的那份。

## status

读 `instance.json`,再回头验证:pid 还在、`/api/system/health` 应答。**文件会说谎,所以一律验证**。

```
memory.talk 运行中(pid 12345)
  地址     http://127.0.0.1:8000
  存储     fs  ~/.memory.talk       ← 或 sqlite ~/.memory.talk/memory.sqlite
  work     3 在做 / 12 总计
  工作单元     2 活着
  已运行   1小时2分
  健康     ok
```

没在跑 → 退出码 1(脚本可判);`--json` 给机器读。

## daemon

前台跑,不 fork、不写 pid,日志到 stdout。`ExecStart=memory.talk server daemon` 给 systemd;容器 ENTRYPOINT 也用它。

## 环境变量

服务读的全部环境变量见 [`../../structure/v5/filesystem.md`](../../structure/v5/filesystem.md#环境变量):`MEMORY_TALK_HOME` / `MEMORY_TALK_STORE` / `MEMORY_TALK_TMUX_SOCKET` / `MEMORY_TALK_TMUXD_*` / 各平台会话记录根。`start` 把当时的环境记进 `instance.json`,`restart` 复用。
