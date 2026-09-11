# work_servers / default_session — 没人声明的协议走 default:协议名当命令名

## 这个场景在测什么
`sleep://` 这种没有专门 server 的协议由 default 接,在 tmux 里跑 `sleep`;调用方看到的只是 scheme,不感知 default;
命令不在 PATH → 400 `cmd_not_found`,而且**登记回滚**(不留半个会话);没有协议的 URI → 400 `bad_uri`。

## fixture 来源
`client`、真 tmux(`needs_tmux`)。
