# work_servers / bash_session — 终端现场的一生

## 这个场景在测什么
`bash://<cwd>` attach:tmux 会话名 = 会话 id、cwd 解析、没配 ttyd 时 `window.url` 老实报 null、把手能力 capture / send;
`capture` 能看到会话里发生的事;reattach 幂等;detach 关闭即回收(会话没了、登记没了、再 capture 404)。

## 不在这测什么
- 结束时冻结 → `freeze`

## fixture 来源
`client`、`svc`、真 tmux(独立 socket,`needs_tmux`)。
