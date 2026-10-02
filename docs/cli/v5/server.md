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

后台拉起 API(uvicorn),等它就绪,把地址、日志路径打出来;关掉终端不会被带走(`start_new_session`)。已经在跑 → 直接打印现状,退出码 0。**先把本机节点起来**([node.md](node.md);已经在跑就不动)——agent 的记录由它推进 trace。

```
memory.talk 已启动(pid 12345)
  地址    http://127.0.0.1:8000
  文档    http://127.0.0.1:8000/docs
  存储    fs  ~/.memory.talk
  日志    ~/.memory.talk/server.log
  节点    memory.talk node status
  停止    memory.talk server stop
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 只绑本机;`0.0.0.0` = 对外(没有鉴权,别在公网这么干) |
| `--port` | `8000` | |
| `--home` | `MEMORY_TALK_HOME` / `~/.memory.talk` | 根;`server.pid` / `server.log` / `instance.json` 都在这 |

起不来(端口被占、依赖缺)→ 把日志尾巴打出来,退出码 1。

## stop

按 `server.pid` 发 SIGTERM,等 5 秒不退再 SIGKILL。没在跑 → 提示,退出码 0。**不动 tmux 会话,也不动节点**——现场活得比服务久,下次 `start` 后按登记重入;节点照读 agent 的记录,中心回来了接着推。

## restart

`stop` + `start`,参数沿用 `instance.json` 里记的那份。

## status

读 `instance.json`,再回头验证:pid 还在、`/api/system/health` 应答。**文件会说谎,所以一律验证**。

```
memory.talk 运行中(pid 12345)
  地址     http://127.0.0.1:8000
  存储     LocalFS  ~/.memory.talk          ← users / auth 的;sqlite 时是 SQLite
  work     ~/.memory.talk/works.db          ← work 固定是这两个 sqlite(/api/system/info 的 works_db / worktrace_db)
  轨迹     ~/.memory.talk/worktrace.db
  启动于   2026-09-05T10:00:00Z
  健康     ok
  停止     memory.talk server stop
```

存储和两个库的路径来自 `/api/system/info`,要登录态;没 setup / 没 login 时那一行提示先做,两个库的行不打。

没在跑 → 退出码 1(脚本可判);`--json` 给机器读。

## daemon

前台跑,不 fork、不写 pid,日志到 stdout。`ExecStart=memory.talk server daemon` 给 systemd;容器 ENTRYPOINT 也用它。

同一个进程听两个口子:`--host` / `--port` 给人和浏览器;`<home>/center.sock`(0600)给本机节点——从它上来的请求身份就是节点,只能读写 `/api/works/{id}/trace`。不起节点([node.md](node.md)),agent 的对话就进不了 trace,别的照常。

## 环境变量

服务读的全部环境变量见 [`../../structure/v5/filesystem.md`](../../structure/v5/filesystem.md#环境变量):`MEMORY_TALK_HOME` / `MEMORY_TALK_STORE`(只管 users / auth)/ `MEMORY_TALK_WORKS_DB` / `MEMORY_TALK_WORKTRACE_DB` / `MEMORY_TALK_TMUX_SOCKET` / `MEMORY_TALK_TMUXD_*` / 各平台会话记录根。`start` 把当时的环境记进 `instance.json`,`restart` 复用。
