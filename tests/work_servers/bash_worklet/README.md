# work_servers / bash_worklet — 终端现场的一生

## 这个场景在测什么
`bash://<cwd>` attach:现场是 tmuxd 的 session(tmux 会话名 = 工作单元 id)、cwd 解析、窗是 tmuxd 自带的 ttyd 地址(`?arg=<id>`)、把手能力只有 send;
没有 capture 端点(读终端归人,打开那扇窗);reattach 幂等;detach 关闭即回收(工作单元没了、登记没了)。

## 不在这测什么
- 结束时冻结 → `freeze`

## fixture 来源
`client`、`svc`、真 tmux(tmuxd 的独立 socket,`needs_tmux`)。
