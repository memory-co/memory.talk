# auth / jwt — token 是 JWT,门在最外层

## 这个场景在测什么
login 发的 token 是 HS256 JWT(`sub` / `iat` / `exp` / `jti`);签名被改、过期、换了 alg 的一律 401,不碰存储;签名对但 `jti` 被 logout 作废的也 401。
门(`gateway.AuthMiddleware`)按路径认凭证:`/api` 只认 Bearer、不认 `mt_surface` cookie(防 CSRF)。

## 不在这测什么
- setup / login / 改密码的流程 → `gate`
- `/surface` 下的 cookie 和 WebSocket → `work_servers/tmuxd_surface`

## fixture 来源
`client`、`svc`(拿 `auth.key` 自己签 token)。
