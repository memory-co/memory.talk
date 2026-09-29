# work_servers / tty_window — 终端窗挂在主路由 /tty 上

## 这个场景在测什么
ttyd 听 unix socket,`tmuxd.asgi()` 挂在 `/tty`;门是 `mt_tty` cookie:没有 → 403;`GET /api/auth/status` 带有效 token 时种上(`Path=/tty`、HttpOnly)→ 页面和 WebSocket 都进得去;logout 清掉、token 作废后同一个 cookie 也不认了;WebSocket 的 Origin 不同源,带着 cookie 也拒(1008)。门在 `gateway.AuthMiddleware`,tmuxd 的 `asgi()` 自己不设门。

## 不在这测什么
- 现场本身的一生(attach / reattach / detach)→ `bash_worklet`
- ttyd 协议细节(字节原样转发,是 tmuxd 的事)

## fixture 来源
`client`、`H`、真 tmux + ttyd(`needs_tmux`)。
