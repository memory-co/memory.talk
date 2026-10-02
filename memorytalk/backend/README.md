# memorytalk/backend —— 服务层

memory.talk 的 FastAPI 服务。`memory.talk server start` 起的就是它;`cli/` 和 `frontend/` 都是它的客户端。这一层只回答三个问题:**请求怎么进来、怎么分层、怎么装配**。每个子目录的用途和重点函数看它自己的 README,这里不重复。

## 分层

```
controllers/   HTTP 面:路由、参数、响应信封;不含业务        → controllers/README.md
services/      业务:每个子包对应一篇设计,入口是 XxxService   → services/README.md
models/        数据形状:请求 / 响应体,也是存储记录的形状     → models/README.md
providers/     存储介质原语:文件系统族 / 数据库族             → providers/README.md
work_servers/  每个协议一个 server,把现场建出来              → work_servers/README.md
```

依赖只往下走:controllers → services → providers;models 谁都能用;work_servers 只被 `services/work_servers` 装载。service 之间不互相 import 内部模块,只通过构造函数注入。

## 一个请求怎么走

1. **进门**(`gateway.py` 的 `AuthMiddleware`,纯 ASGI,包在最外层,HTTP 和 WebSocket 都管):`/api/*` 除了 `auth/status`、`auth/setup`、`auth/login`、`system/health` 只认 Bearer JWT;`/surface/*`(窗)只认 `mt_surface` cookie,WebSocket 另验 Origin。没有 admin → `/api` 409 `setup_required`;没有效凭证 → 401(`/surface` 403 / close 1008);过了门,名字放进 `request.state.user`。设计:[auth.md](../../docs/designs/v5/auth.md)。
2. **路由**(`controllers/`):从 `request.app.state` 拿 service,调一个方法,`ok()` 包成 `{data, message}`。
3. **业务**(`services/`):只认仓储接口和别的 service,不认识 HTTP。出错抛自己的异常类。
4. **错误映射**(`main.py`):`WorkNotFound` / `UserNotFound` / `WorkletNotFound` → 404,`WorkConflict` → 409,`UserExists` → 409,`MetasError` / `AuthError` / `WorkServerError` 各带自己的状态码;都变成 `{data: null, message, error}`。
5. **前端**(`gateway.py`):有构建产物就在 `/` 托管 `index.html`、`/assets` 托管静态资源;不拦。
6. **窗**(`/surface/*`):终端是 `/surface/tmuxd`,`tmuxd.asgi()` 挂在这里,经 unix socket 原样转给 ttyd;门在第 1 步,它自己不设。

## 装配

`main.py` 的 `create_app(config, runtime)`:

- `config.py`:`Config`(`MEMORY_TALK_HOME`、git author 默认名、`works_db` / `worktrace_db` 两个库的路径)和 `RuntimeConfig`(workspace、tmuxd 的 socket 名和 state 目录、各平台会话记录根)。全部来自环境变量,没有配置文件。
- `StoreService` 开 work 的两个 sqlite(`works.db` / `worktrace.db`,各一个 provider 实例),按 `MEMORY_TALK_STORE` 给 users / auth 选 provider;`MetasService` 自己开 git 仓库;`WorkServerService` 装载 `work_servers/`;`WorkService`、`UserService`、`AuthService`、`SearchService` 依次注入。全部挂在 `app.state`,测试直接 `create_app()` 起一个。
- `lifespan`:起一个后台任务,每 30 秒把心跳超时的人清出 `works.viewers`;退出时取消它、收掉 ttyd。

## 边界

- 存储三处:work 固定是两个 sqlite——`works.db` 管现在(节点、列、登记和摆在哪、收件箱),`worktrace.db` 管经过(段、点、round);user / token 的记录走 provider(fs 或 sqlite,测试两种都跑);metas 是一个 git 仓库。服务进程是唯一写者。
- 现场(tmux 会话)不由这里持有状态:活没活着每次问 server。
- 未做:ttyd 反代托管(挂公网时窗要么 0.0.0.0 + token,要么自己反代)、逐 round 标注、二进制 blob 外置、给人手工 `git commit` 用的 hook。

端点清单 [docs/api/v5](../../docs/api/v5/README.md);设计 [docs/designs/v5](../../docs/designs/v5/README.md);测试在仓库根 `pytest`。
