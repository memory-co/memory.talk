# test_no_config_start

零配置启动场景 —— 只给空的 data_root(加一个随机端口避免冲突),其它全走默认。

## 场景

```
空 ~/.memory-talk/(只写一个 {"server": {"port": <random>}})
   ↓
memory-talk server start --data-root=<tmp>
   ↓
uvicorn 子进程起来 → 默认 dummy embedder → 无网络调用
   ↓
GET /v2/status → {status: running, embedding_provider: dummy, ...}
   ↓
memory-talk server stop
```

## 覆盖的路径

- CLI `server start`:parse args → `Config.validate()`(空 data_root 通过)→
  `subprocess.Popen([uvicorn, ...])` → 等 1.2s → 写 pid 文件 → 打 JSON
- `server stop`:读 pid → `os.kill(SIGTERM)` → 删 pid 文件
- uvicorn 子进程完整生命周期:lifespan startup → SQLiteStore.create →
  LanceStore.create → `validate_embedder()`(dummy 立即通过)→ 绑定 route
- `GET /v2/status` 真正走 TCP(不是 ASGI transport)

## 关键断言

- `server start` 返回 `{status: started, pid, port}`
- `GET /v2/status` 返回 `status: running`、`embedding_provider: dummy`
- 空 data root:`sessions_total=0`、`cards_total=0`、`links_total=0`、`searches_total=0`
- `server stop` 返回 `{status: stopped, pid}`

## 和 sync 场景的区别

sync 测试用 `httpx.ASGITransport(app)` 进程内路由 —— 不起子进程、不绑端口。
server 测试的重点**就是**起 uvicorn 子进程的生命周期,无法用 ASGI 代替。

## 清理

`conftest.py::server_env` 的 finalizer 总会调 `server stop`,即使 test
中途 raise,避免留下游离的 uvicorn 进程。

## 失败诊断

- "server never became ready on :<port>" —— subprocess 起来了但 HTTP 不响应。
  通常是 lifespan startup 卡住(SQLite/LanceDB 初始化)。
- "start result: {status: failed, error: ...}" —— Config.validate() 或
  `validate_embedder()` 在 lifespan 里 raise 了 SystemExit(2)。看 error
  字段拿具体原因。
