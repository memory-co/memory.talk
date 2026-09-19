# auth —— 门

对应后端 `/api/auth`(设计:[auth.md](../../../../docs/designs/v5/auth.md))。

| 文件 | 重点 |
|---|---|
| `Gate.tsx` | `Gate`:进来先问 `GET /auth/status`(按当前 token 缓存)。`setup_required` → `<Setup/>`;没 token 或 token 不认了 → `<Login/>`;否则 `<Shell/>`。token 变空时清掉别的查询缓存,免得换人后看到上一个人的数据 |
| `Setup.tsx` | `Setup`:还没有 admin 时的页面——显示名 + 密码 + 确认,`POST /auth/setup` 成功就 `setSession` 进壳 |
| `Login.tsx` | `Login`:用户名 + 密码,`POST /auth/login`;用户名预填上次登录的名字(退出时留着) |

token 本身存在 `lib/store.ts`,由 `lib/api.ts` 带上;任何请求 401 都会清登录态回到这里。
