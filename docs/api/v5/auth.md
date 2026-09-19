# Auth API

门。机制见 [designs auth.md](../../designs/v5/auth.md):没有 `admin` 账号时先 setup;有了之后所有 `/api/*`(除本页的 status / setup / login 和 `/api/system/health`)都要 `Authorization: Bearer <token>`,否则 401 `unauthorized`。身份从 token 来,`X-Memory-Talk-User` 头被忽略。

## GET /api/auth/status

```json
{"setup_required": false, "authenticated": true, "user": {"name": "alice", "display_name": "Alice", "email": "…", "created_at": "…", "role": "member"}}
```

不拦。`setup_required` = 还没有 admin;`authenticated` = 这次带的 token 有效;`user` = token 对应的账号(没带 / 无效 → `null`)。前端进来先问它。

## POST /api/auth/setup

```json
{"password": "至少 6 位", "display_name": "可选", "email": "可选"}
```

建 `admin`(role `admin`)并登录,**201** 返回 `{token, user}`。admin 已存在 → 404 `not_found`。没 admin 之前其它端点一律 409 `setup_required`。

## POST /api/auth/login

```json
{"name": "alice", "password": "…"}
```

**200** `{token, user}`。名字或密码不对 → 401 `unauthorized`(不区分哪个不对)。没设过密码的账号登不进。token 不过期;换密码会作废这个人的全部 token。

## POST /api/auth/logout

作废这次带的 token。返回 `{}`。

## 错误

| 状态 | error | 什么时候 |
|---|---|---|
| 401 | `unauthorized` | 没带 token / token 不认识 / 密码不对 / 改自己密码旧密码不对 |
| 403 | `forbidden` | member 做 admin 的事(建账号、给别人设密码、改别人档案) |
| 409 | `setup_required` | 还没 admin |
