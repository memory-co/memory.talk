# controllers —— HTTP 面

FastAPI 路由。**只做参数 / 响应,不含业务**:每个文件一个 `router`,从 `request.app.state` 取 service,调一个方法,用 `ok()` 包成 `{data, message}` 信封。错误不在这里处理——service 抛的异常由 `main.py` 里注册的 handler 映射成状态码。

| 文件 | 前缀 | 重点 |
|---|---|---|
| `auth.py` | `/api/auth` | `status` / `setup` / `login` / `logout`。还提供三个给别的 controller 用的依赖:`bearer(request)` 取 token、`current_user(request)` 取门放进 `request.state.user` 的名字、`require_admin(request)` 不是 admin 就 403 |
| `users.py` | `/api/users` | `list_users` / `register`(admin)/ `me` / `get_user` / `update_user`(自己或 admin)/ `set_password`(自己带旧密码,admin 给别人不用) |
| `works.py` | `/api/works` | 树:`forest` / `create` / `get` / `update`;`events` / `inbox` / `get_manager` / `put_manager`;`users` / `touch`;画布 `get_canvas` / `put_canvas`;工作单元 `worklets` / `attach` / `reattach` / `detach` / `capture` / `rounds`;`servers`。`user(request)` 依赖 = 登录态里的名字 |
| `metas.py` | `/api/metas` | `layers` / `config` / `tree` / `recent` / `history`;对象 `create`(POST)/ `get` / `update`(PUT)/ `delete`。`ctx()` 依赖把登录态 + `X-Memory-Talk-Work` 头拼成 `Ctx`;`_files()` 把请求体变成目录里的文件改动(origin 用 content);`_dry()` 把 dry_run 的结果包成 `CheckResult`。manager 相关路由暂时注释掉,等 work 那边实现 |
| `search.py` | `/api/search` | `search(q, limit)` → SearchService |
| `system.py` | `/api/system` | `health`(不拦)/ `info` |

固定路径要放在 `/{layer}/{path:path}` 这种通配路由前面(metas.py 里有注释标着)。
